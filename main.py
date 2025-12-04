import click
import time
import sys
from config import load_config, validate_config
from database import connect_db, test_connection, get_vacation_info, get_schema, execute_query, format_schema_for_llm
from llm import test_openrouter, generate_sql, generate_response, fix_sql_error, clean_sql_response
from vacation import load_vacation_data, format_vacation_info
from utils import is_safe_query, clean_sql

# Color codes for CLI output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_success(message):
    """Print success message in green."""
    print(f"{Colors.GREEN}✓ {message}{Colors.ENDC}")

def print_error(message):
    """Print error message in red."""
    print(f"{Colors.RED}✗ {message}{Colors.ENDC}")

def print_warning(message):
    """Print warning message in yellow."""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.ENDC}")

def print_info(message):
    """Print info message in blue."""
    print(f"{Colors.BLUE}ℹ {message}{Colors.ENDC}")

def print_header(message):
    """Print header message in bold."""
    print(f"{Colors.BOLD}{Colors.HEADER}=== {message} ==={Colors.ENDC}")

def format_question_answer(question, answer, elapsed_time=None):
    """Format question and answer nicely."""
    print(f"\n{Colors.BOLD}Question:{Colors.ENDC} {question}")
    print(f"{Colors.BOLD}Answer:{Colors.ENDC} {answer}")
    if elapsed_time:
        print(f"{Colors.BLUE}Processing time: {elapsed_time:.2f}s{Colors.ENDC}")

def format_table(data, headers=None):
    """Format data as a simple table."""
    if not data:
        return "No data to display."
    
    if isinstance(data, list) and len(data) > 0:
        if not headers and isinstance(data[0], dict):
            headers = list(data[0].keys())
        
        if headers:
            # Calculate column widths
            widths = [len(str(h)) for h in headers]
            for row in data[:10]:  # Only check first 10 rows for width
                for i, header in enumerate(headers):
                    value = str(row.get(header, '')) if isinstance(row, dict) else str(row[i] if i < len(row) else '')
                    widths[i] = max(widths[i], len(value))
            
            # Print header
            header_row = " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers))
            print(f"{Colors.BOLD}{header_row}{Colors.ENDC}")
            print("-" * len(header_row))
            
            # Print rows (limit to first 10)
            for i, row in enumerate(data[:10]):
                if isinstance(row, dict):
                    values = [str(row.get(h, '')) for h in headers]
                else:
                    values = [str(row[i] if i < len(row) else '') for i in range(len(headers))]
                row_str = " | ".join(val.ljust(widths[i]) for i, val in enumerate(values))
                print(row_str)
            
            if len(data) > 10:
                print(f"{Colors.YELLOW}... and {len(data) - 10} more rows{Colors.ENDC}")
        else:
            # Simple list display
            for i, item in enumerate(data[:10]):
                print(f"{i+1}. {item}")
            if len(data) > 10:
                print(f"{Colors.YELLOW}... and {len(data) - 10} more items{Colors.ENDC}")
    else:
        print(str(data))

@click.group()
def cli():
    """Simple SQL Agent CLI."""
    pass

def is_vacation_question(question):
    """Check if question is about vacation/time off."""
    vacation_keywords = [
        'vacation', 'holiday', 'time off', 'leave', 'sick',
        'отпуск', 'каникулы', 'больничный',
        'відпуст', 'канікул', 'лікарн'
    ]
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in vacation_keywords)

def process_question_with_retry(question, config, debug=False, max_retries=2):
    """Process a question with retry logic for better results."""
    
    for attempt in range(max_retries + 1):
        if debug and attempt > 0:
            print(f"\n=== RETRY ATTEMPT {attempt} ===")
        
        result = process_question(question, config, debug, attempt)
        
        # If we got a result and it's not a "no results" error, return it
        if result and not result.startswith("No results found"):
            return result
        
        # If this was the last attempt, return the result anyway
        if attempt == max_retries:
            return result
            
        # For retry attempts, try modified question approaches
        if attempt == 0:
            # First retry: try with broader time range
            modified_question = question.replace("последн", "за 2025 год").replace("recent", "in 2025").replace("last week", "in November 2025")
            if debug:
                print(f"Retrying with modified question: {modified_question}")
            question = modified_question
    
    return "Unable to find results after multiple attempts."

def process_question(question, config, debug=False, attempt=0):
    """Process a natural language question end-to-end."""
    start_time = time.time()
    
    try:
        if debug:
            print(f"\n=== DEBUG MODE ===")
            print(f"Question: {question}")
            print(f"Vacation question: {is_vacation_question(question)}")
        
        # Step 1: Get database schema
        if debug:
            print_header("Step 1: Getting database schema")
        else:
            print_info("Getting database schema...")
        
        schema = get_schema(config)
        if not schema:
            return "Error: Unable to retrieve database schema."
        
        if debug:
            print_success(f"Schema loaded: {len(schema)} tables")
            for table_name in schema.keys():
                print(f"  - {table_name}")
        
        # Step 2: Generate SQL
        if debug:
            print_header("Step 2: Generating SQL")
        else:
            print_info("Generating SQL query...")
        
        sql = generate_sql(config, question, schema)
        if not sql:
            return "Error: Unable to generate SQL query for your question."
        
        if debug:
            print_success(f"Generated SQL: {sql}")
        
        # Step 3: Execute SQL with safety checks
        if debug:
            print_header("Step 3: Executing SQL")
        else:
            print_info("Executing query...")
        
        # Clean the SQL
        sql = clean_sql(sql)
        if not sql:
            return "Error: Generated SQL is empty or invalid."
        
        # Safety check
        if not is_safe_query(sql):
            return "Error: Generated SQL query contains unsafe operations."
        
        # Execute query
        results = execute_query(config, sql)
        
        # Step 4: Handle SQL errors and retry if needed
        if results is None:
            if debug:
                print_header("Step 4: SQL failed, attempting to fix")
            else:
                print_warning("Query failed, trying to fix...")
            
            # Try to fix the SQL once
            fixed_sql = fix_sql_error(config, sql, "Query execution failed", schema)
            if fixed_sql:
                fixed_sql = clean_sql(fixed_sql)
                if fixed_sql and is_safe_query(fixed_sql):
                    if debug:
                        print_success(f"Fixed SQL: {fixed_sql}")
                    results = execute_query(config, fixed_sql)
                    sql = fixed_sql  # Use fixed SQL for response generation
        
        # Check if we have results
        if results is None:
            return "Error: Unable to execute SQL query after attempting to fix it."
        
        if isinstance(results, dict) and 'error' in results:
            return f"Database error: {results['error']}"
        
        if debug:
            print(f"Query results: {len(results) if isinstance(results, list) else 1} rows")
        
        # Step 5: Handle vacation questions specially
        vacation_context = ""
        if is_vacation_question(question):
            if debug:
                print_header("Step 5: Adding vacation context")
            else:
                print_info("Adding vacation context...")
            
            try:
                vacation_data = load_vacation_data()
                if vacation_data:
                    vacation_context = f"\n\nVacation data is also available with {vacation_data.get('n_users', 0)} users and {vacation_data.get('n_requests', 0)} vacation requests."
                    if debug:
                        print_success(f"Added vacation context: {vacation_data.get('n_users', 0)} users, {vacation_data.get('n_requests', 0)} requests")
            except Exception as e:
                if debug:
                    print_warning(f"Vacation context failed: {e}")
        
        # Step 6: Generate natural language response
        if debug:
            print_header("Step 6: Generating response")
        else:
            print_info("Generating response...")
        
        enhanced_question = question + vacation_context
        response = generate_response(config, enhanced_question, results)
        
        if not response:
            # Fallback to basic summary
            if isinstance(results, list):
                response = f"Found {len(results)} results for your query."
            else:
                response = "Query executed successfully."
        
        # Add timing info
        elapsed_time = time.time() - start_time
        if debug:
            print(f"\n--- Processing complete in {elapsed_time:.2f} seconds ---")
        
        return response
        
    except Exception as e:
        if debug:
            print(f"\n--- Error in processing ---")
            print(f"Error: {e}")
        return f"Error processing question: {str(e)}"

@cli.command()
def setup():
    """Check configuration and database connection."""
    try:
        print("Checking configuration...")
        config = load_config()
        validate_config(config)
        print("✓ Configuration valid")
        
        print("Testing database connection...")
        if test_connection(config):
            print("✓ Database connection successful")
        else:
            print("✗ Database connection failed")
            return
        
        print("Testing OpenRouter connection...")
        if test_openrouter(config):
            print("✓ OpenRouter connection successful")
        else:
            print("✗ OpenRouter connection failed")
            return
            
        print("\nSetup complete! You can now use 'ask' command.")
        
    except Exception as e:
        print_error(f"Setup failed: {e}")
        if "Missing required configuration" in str(e):
            print_info("💡 Tip: Copy .env.example to .env and fill in your database and API credentials")

@cli.command()
@click.argument('question')
def ask(question):
    """Ask a natural language question."""
    try:
        config = load_config()
        validate_config(config)
        
        start_time = time.time()
        answer = process_question_with_retry(question, config, debug=False)
        elapsed_time = time.time() - start_time
        
        format_question_answer(question, answer, elapsed_time)
        
    except Exception as e:
        print_error(f"Configuration error: {e}")
        if "Missing required configuration" in str(e):
            print_info("💡 Tip: Copy .env.example to .env and fill in your database and API credentials")

@cli.command()
def test_db():
    """Test database connection."""
    try:
        config = load_config()
        print("Testing database connection...")
        
        if test_connection(config):
            print("✓ Database connection successful")
        else:
            print("✗ Database connection failed")
            
    except Exception as e:
        print(f"Database test failed: {e}")

@cli.command()
def test_llm():
    """Test OpenRouter connection."""
    try:
        config = load_config()
        print("Testing OpenRouter connection...")
        
        if test_openrouter(config):
            print("✓ OpenRouter connection successful")
        else:
            print("✗ OpenRouter connection failed")
            
    except Exception as e:
        print(f"OpenRouter test failed: {e}")

@cli.command()
def test_vacation():
    """Test vacation data loading."""
    try:
        print("Testing vacation data loading...")
        vacation_data = load_vacation_data()
        
        if vacation_data:
            users_count = vacation_data.get('n_users', 0)
            requests_count = vacation_data.get('n_requests', 0)
            print(f"✓ Vacation data loaded successfully")
            print(f"  {users_count} users, {requests_count} requests")
        else:
            print("✗ Failed to load vacation data")
            
    except Exception as e:
        print(f"Vacation test failed: {e}")

@cli.command()
@click.argument('employee_id', type=int)
@click.option('--year', type=int, help='Specific year to query')
def vacation(employee_id, year):
    """Get vacation information for employee."""
    try:
        config = load_config()
        validate_config(config)
        
        print(f"Getting vacation info for employee {employee_id}...")
        if year:
            print(f"Filtering for year {year}")
        
        vacation_info = get_vacation_info(config, employee_id, year)
        
        if 'error' in vacation_info:
            print(f"Error: {vacation_info['error']}")
        else:
            formatted_info = format_vacation_info(vacation_info)
            print(formatted_info)
            
    except Exception as e:
        print(f"Vacation query failed: {e}")

@cli.command()
def load_vacation():
    """Load and process vacation data."""
    try:
        config = load_config()
        validate_config(config)
        
        from vacation import load_vacation_data, match_vacation_users, calculate_vacation_days
        
        # Load vacation data
        vacation_data = load_vacation_data()
        if not vacation_data:
            print("Failed to load vacation data")
            return
        
        # Match users
        user_mapping = match_vacation_users(vacation_data, config)
        if not user_mapping:
            print("Failed to match vacation users")
            return
        
        # Calculate vacation days
        vacation_summary = calculate_vacation_days(vacation_data, user_mapping)
        if not vacation_summary:
            print("Failed to calculate vacation data")
            return
        
        print("\nVacation data processing complete!")
        print(f"Processed data for {len(vacation_summary)} employees")
        
    except Exception as e:
        print(f"Vacation loading failed: {e}")

@cli.command()
@click.argument('question')
def debug(question):
    """Ask a question with detailed debugging information."""
    try:
        config = load_config()
        validate_config(config)
        
        print(f"Question: {question}")
        answer = process_question(question, config, debug=True)
        print(f"\nFinal Answer: {answer}")
        
    except Exception as e:
        print_error(f"Debug failed: {e}")
        if "Missing required configuration" in str(e):
            print_info("💡 Tip: Copy .env.example to .env and fill in your database and API credentials")

@cli.command()
def interactive():
    """Start interactive question session."""
    try:
        config = load_config()
        validate_config(config)
        
        # Initialize conversation history
        history = []
        
        print_header("SQL Agent Interactive Mode")
        print_info("Welcome to the SQL Agent! Ask questions about your database in natural language.")
        print()
        print("📋 Available commands:")
        print("  • help          - Show help and examples")
        print("  • history       - Show conversation history")
        print("  • clear         - Clear conversation history")
        print("  • status        - Show system status")
        print("  • debug <q>     - Process question with detailed debugging")
        print("  • exit/quit     - Exit interactive mode")
        print()
        print("🌟 Example questions:")
        print("  • How many employees are in the Alpha team?")
        print("  • Who is currently on vacation?")
        print("  • Show me the most active projects this week")
        print("-" * 70)
        
        while True:
            try:
                question = input(f"\n{Colors.BOLD}Question:{Colors.ENDC} ").strip()
                
                if question.lower() in ['exit', 'quit']:
                    print_success("Goodbye! Thanks for using SQL Agent.")
                    break
                
                if not question:
                    continue
                
                # Handle special commands
                if question.lower() == 'help':
                    print_info("SQL Agent Help")
                    print()
                    print("🎯 What I can do:")
                    print("  • Answer questions about employees, teams, projects")
                    print("  • Calculate project statistics and time tracking")
                    print("  • Show vacation information and leave balances")
                    print("  • Analyze team composition and specializations")
                    print()
                    print("💡 Tips for better results:")
                    print("  • Be specific about what you want to know")
                    print("  • Mention team names (Alpha, Beta, Fusion, etc.)")
                    print("  • Ask about time periods (this week, last month, etc.)")
                    print("  • Use 'debug <question>' to see processing steps")
                    continue
                
                if question.lower() == 'history':
                    if history:
                        print_info(f"Conversation History ({len(history)} questions)")
                        for i, (q, a, t) in enumerate(history, 1):
                            print(f"{i}. {Colors.BOLD}Q:{Colors.ENDC} {q}")
                            print(f"   {Colors.BOLD}A:{Colors.ENDC} {a[:100]}{'...' if len(a) > 100 else ''}")
                            print(f"   {Colors.BLUE}Time: {t:.2f}s{Colors.ENDC}")
                    else:
                        print_warning("No conversation history yet.")
                    continue
                
                if question.lower() == 'clear':
                    history.clear()
                    print_success("Conversation history cleared.")
                    continue
                
                if question.lower() == 'status':
                    # Run a mini status check
                    print_info("Quick status check...")
                    try:
                        schema = get_schema(config)
                        if schema:
                            print_success(f"Database: Connected ({len(schema)} tables)")
                        else:
                            print_error("Database: Connection issue")
                    except:
                        print_error("Database: Connection issue")
                    continue
                
                # Check if debug mode requested
                debug_mode = False
                if question.lower().startswith('debug '):
                    debug_mode = True
                    question = question[6:].strip()
                
                if not question:
                    print_warning("Please provide a question after 'debug'")
                    continue
                
                # Process the question
                start_time = time.time()
                answer = process_question_with_retry(question, config, debug=debug_mode)
                elapsed_time = time.time() - start_time
                
                # Display result
                if not debug_mode:
                    print(f"\n{Colors.BOLD}Answer:{Colors.ENDC} {answer}")
                    print_info(f"Processing time: {elapsed_time:.2f}s")
                else:
                    print(f"\n{Colors.BOLD}Final Answer:{Colors.ENDC} {answer}")
                
                # Add to history
                history.append((question, answer, elapsed_time))
                
                print("-" * 70)
                
            except KeyboardInterrupt:
                print("\n")
                print_success("Goodbye! Thanks for using SQL Agent.")
                break
            except Exception as e:
                print_error(f"Error processing question: {e}")
                
    except Exception as e:
        print_error(f"Interactive mode failed: {e}")
        if "Missing required configuration" in str(e):
            print_info("💡 Tip: Copy .env.example to .env and fill in your database and API credentials")

@cli.command()
def test_questions():
    """Run the 4 required test questions."""
    test_questions_list = [
        "How much on average do task estimates exceed actual time spent for Alpha team?",
        "What is the most active project in Fusion team by hours logged last week?",
        "Describe the composition of each team by developer specialization",
        "How many vacation days has each Alpha team member taken since the beginning of the year?"
    ]
    
    try:
        config = load_config()
        validate_config(config)
        
        print_header("Running Test Questions")
        print_info(f"Testing {len(test_questions_list)} questions...\n")
        
        for i, question in enumerate(test_questions_list, 1):
            print_header(f"Test Question {i}/{len(test_questions_list)}")
            print(f"{Colors.BOLD}Question:{Colors.ENDC} {question}")
            
            start_time = time.time()
            answer = process_question_with_retry(question, config, debug=False)
            elapsed_time = time.time() - start_time
            
            print(f"{Colors.BOLD}Answer:{Colors.ENDC} {answer}")
            print_info(f"Processing time: {elapsed_time:.2f}s")
            print("-" * 80)
            
        print_success("All test questions completed!")
        
    except Exception as e:
        print_error(f"Test questions failed: {e}")
        if "Missing required configuration" in str(e):
            print_info("💡 Tip: Copy .env.example to .env and fill in your database and API credentials")

@cli.command()
def status():
    """Show system status and health check."""
    print_header("SQL Agent System Status")
    
    try:
        config = load_config()
        
        # Test configuration
        try:
            validate_config(config)
            print_success("Configuration: Valid")
        except Exception as e:
            print_error(f"Configuration: {e}")
        
        # Test database connection
        try:
            if test_connection(config):
                print_success("Database connection: Connected")
                
                # Get schema info
                schema = get_schema(config)
                if schema:
                    print_info(f"Database schema: {len(schema)} tables available")
                    table_names = ", ".join(sorted(schema.keys()))
                    print(f"  Tables: {table_names}")
                else:
                    print_warning("Database schema: Unable to retrieve")
            else:
                print_error("Database connection: Failed")
        except Exception as e:
            print_error(f"Database connection: Error - {e}")
        
        # Test LLM API
        try:
            if test_openrouter(config):
                print_success("LLM API: Connected")
                model = config.get('llm_model', 'anthropic/claude-3.5-sonnet')
                print_info(f"LLM model: {model}")
            else:
                print_error("LLM API: Failed")
        except Exception as e:
            print_error(f"LLM API: Error - {e}")
        
        # Test vacation data
        try:
            vacation_data = load_vacation_data()
            if vacation_data:
                users = vacation_data.get('n_users', 0)
                requests = vacation_data.get('n_requests', 0)
                print_success(f"Vacation data: Loaded ({users} users, {requests} requests)")
            else:
                print_warning("Vacation data: Not available")
        except Exception as e:
            print_warning(f"Vacation data: Warning - {e}")
        
        # System settings
        print_info(f"Response language: {config.get('response_language', 'auto')}")
        print_info(f"Debug mode: {config.get('debug', False)}")
        print_info(f"LLM timeout: {config.get('llm_timeout', 30)}s")
        
    except Exception as e:
        print_error(f"Status check failed: {e}")

@cli.command()
def test():
    """Run the test suite."""
    try:
        print_header("SQL Agent Test Suite")
        print_info("Running comprehensive system tests...\n")
        
        # Import test module
        import test as test_module
        
        # Run all tests
        success = test_module.run_all_tests()
        
        if success:
            print_success("\nAll tests completed successfully!")
        else:
            print_warning("\nSome tests failed. Check output above for details.")
            print_info("💡 Tip: Many test failures are expected without proper database and API configuration")
        
        return success
        
    except ImportError:
        print_error("Test module not found. Make sure test.py exists.")
        return False
    except Exception as e:
        print_error(f"Test execution failed: {e}")
        return False

if __name__ == '__main__':
    cli()