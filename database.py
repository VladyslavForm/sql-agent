import psycopg2
import psycopg2.extras

def is_safe_sql(sql):
    """Check if SQL query is safe to execute."""
    if not sql:
        return False
        
    # Clean and normalize SQL for checking
    sql_upper = sql.strip().upper()
    
    # Must start with SELECT (only read operations allowed)
    if not sql_upper.startswith('SELECT') and not sql_upper.startswith('WITH'):
        return False
    
    # Block dangerous DDL/DML keywords at statement boundaries
    dangerous_patterns = [
        r'\bDROP\s+TABLE\b', r'\bDROP\s+DATABASE\b', r'\bDROP\s+SCHEMA\b',
        r'\bDELETE\s+FROM\b', r'\bINSERT\s+INTO\b', r'\bUPDATE\s+\w+\s+SET\b',
        r'\bTRUNCATE\s+TABLE\b', r'\bALTER\s+TABLE\b', r'\bCREATE\s+TABLE\b',
        r'\bCREATE\s+DATABASE\b', r'\bCREATE\s+SCHEMA\b'
    ]
    
    import re
    for pattern in dangerous_patterns:
        if re.search(pattern, sql_upper):
            return False
    
    # Basic SQL injection patterns
    injection_patterns = [';--', '/*', '*/', 'OR 1=1', 'OR 1 = 1']
    for pattern in injection_patterns:
        if pattern.upper() in sql_upper:
            return False
    
    return True

def add_limit_if_needed(sql):
    """Add LIMIT clause to SELECT queries if not present."""
    if not sql:
        return sql
        
    sql_stripped = sql.strip()
    sql_upper = sql_stripped.upper()
    
    # Only modify SELECT statements
    if not sql_upper.startswith('SELECT'):
        return sql
        
    # Check if LIMIT already exists
    if 'LIMIT' in sql_upper:
        return sql
        
    # Remove trailing semicolon if present, add LIMIT, then add semicolon back
    if sql_stripped.endswith(';'):
        return sql_stripped[:-1] + ' LIMIT 1000;'
    else:
        return sql_stripped + ' LIMIT 1000'

def connect_db(config):
    """Connect to PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=config['db_host'],
            port=config['db_port'],
            database=config['db_name'],
            user=config['db_user'],
            password=config['db_password']
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def execute_query(config, sql):
    """Execute SQL query and return results."""
    if not sql:
        print("Error: Empty SQL query")
        return None
        
    # Safety check
    if not is_safe_sql(sql):
        print(f"Warning: Unsafe SQL query blocked: {sql}")
        return {"error": "Unsafe SQL query blocked"}
        
    # Add LIMIT for SELECT queries if needed
    sql = add_limit_if_needed(sql)
    
    conn = None
    try:
        conn = connect_db(config)
        if not conn:
            return None
            
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(sql)
        
        # Check if this is a SELECT query (including WITH clauses that end with SELECT)
        sql_upper = sql.strip().upper()
        if sql_upper.startswith('SELECT') or (sql_upper.startswith('WITH') and 'SELECT' in sql_upper):
            results = cursor.fetchall()
            # Convert Decimal objects to float for JSON serialization
            import decimal
            converted_results = []
            for row in results:
                converted_row = {}
                for key, value in dict(row).items():
                    if isinstance(value, decimal.Decimal):
                        converted_row[key] = float(value)
                    else:
                        converted_row[key] = value
                converted_results.append(converted_row)
            return converted_results
        else:
            conn.commit()
            return {"status": "success"}
            
    except Exception as e:
        print(f"Query execution error: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def setup_database_from_file(config, sql_file_path):
    """Set up database from SQL file."""
    try:
        print(f"Reading SQL file: {sql_file_path}")
        with open(sql_file_path, 'r') as file:
            sql_content = file.read()
        
        if not sql_content.strip():
            print("Warning: SQL file is empty")
            return False
        
        print("Setting up database...")
        conn = None
        try:
            conn = connect_db(config)
            if not conn:
                print("Error: Could not connect to database")
                return False
                
            cursor = conn.cursor()
            
            # Split SQL content by statements (simple approach)
            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
            
            for i, statement in enumerate(statements):
                try:
                    print(f"Executing statement {i+1}/{len(statements)}")
                    cursor.execute(statement)
                except Exception as e:
                    print(f"Error in statement {i+1}: {e}")
                    continue
                    
            conn.commit()
            print("✓ Database setup completed successfully")
            return True
            
        except Exception as e:
            print(f"Database setup error: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
                
    except FileNotFoundError:
        print(f"Error: SQL file not found: {sql_file_path}")
        return False
    except Exception as e:
        print(f"File reading error: {e}")
        return False

def get_schema(config):
    """Get database schema information."""
    schema_query = """
    SELECT 
        table_name,
        column_name,
        data_type,
        is_nullable
    FROM information_schema.columns 
    WHERE table_schema = 'public'
    ORDER BY table_name, ordinal_position;
    """
    
    try:
        results = execute_query(config, schema_query)
        if not results:
            return None
            
        tables = {}
        for row in results:
            table = row['table_name']
            if table not in tables:
                tables[table] = []
            tables[table].append({
                'column': row['column_name'],
                'type': row['data_type'],
                'nullable': row['is_nullable']
            })
        return tables
        
    except Exception as e:
        print(f"Schema retrieval error: {e}")
        return None

def format_schema_for_llm(schema):
    """Format database schema for LLM context with business context and examples."""
    if not schema:
        return "No schema available"
        
    # Enhanced schema with business context and sample data
    enhanced_schema = """
DATABASE SCHEMA with Business Context and Examples:

Table: team
  team_id integer NOT NULL (Primary Key)
  name varchar NOT NULL
  date_created timestamp
  date_updated timestamp
  Description: Teams in the company (Alpha, Fusion, DL, etc.). Contains 13 teams total.
  Sample data: Alpha (11 employees), Fusion (28 employees), DL (5 employees)

Table: employee  
  employee_id integer NOT NULL (Primary Key)
  name varchar NOT NULL
  team_id integer NOT NULL (Foreign Key → team.team_id)
  position varchar NOT NULL (e.g., "Программист, 12, middle", "Team lead 113 lvl")
  start_date date
  vacation_left integer (remaining vacation days, typically 0-20)
  clickup_id varchar (links to ClickUp user)
  Description: Company employees with their positions and team assignments.
  Sample data: 103 employees total across all teams

Table: project
  project_id integer NOT NULL (Primary Key)  
  name varchar NOT NULL
  team varchar NOT NULL (team name like "Fusion", "Alpha")
  status varchar (project status)
  time_spent bigint (total time in SECONDS - divide by 3600 for hours)
  date_created timestamp  
  date_updated timestamp (last update, data available until 2025-11-21)
  clickup_id varchar (ClickUp project identifier)
  Description: Company projects with time tracking. Time is in SECONDS!
  Sample data: "Keystone" (100B+ seconds), "Admiral Markets" (47B+ seconds)

Table: task
  task_id integer NOT NULL (Primary Key)
  name varchar NOT NULL
  clickup_id varchar
  time_estimate bigint (estimated time in SECONDS)
  time_spent bigint (actual time spent in SECONDS) 
  date_created timestamp
  date_updated timestamp (data available until 2025-11-21)
  status varchar
  Description: Individual tasks with time estimates vs actual time spent.
  
Table: task_employee
  task_id integer (Foreign Key → task.task_id)
  employee_id integer (Foreign Key → employee.employee_id)
  Description: Links employees to tasks they work on.

Table: project_employee
  project_id integer (Foreign Key → project.project_id)
  employee_id integer (Foreign Key → employee.employee_id)  
  Description: Links employees to projects they work on.

Table: developer
  developer_id integer NOT NULL (Primary Key)
  clickup_id varchar (links to employee)
  specialization varchar (like "Frontend", "Backend", "QA")
  Description: Developer specialization information.

IMPORTANT NOTES:
- ALL TIME VALUES are in SECONDS (divide by 3600 to get hours)
- Data is available until 2025-11-21, use this date range for recent queries
- Team names: Alpha, Fusion, DL, Finance, HR & Recruiting, International, Marketing, Oyster, Pink Goose, Presales, Zoo, Sales, Reactor
- To find team activity, join project → task → task_employee → employee → team
- To find vacation info, check vacation_left field or use vacation system
"""
    
    return enhanced_schema.strip()

def test_connection(config):
    """Test database connection."""
    try:
        print("Attempting database connection...")
        conn = connect_db(config)
        if conn:
            print("Connection established, testing query execution...")
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            conn.close()
            if result is not None:
                print("✓ Database connection test successful")
                return True
            else:
                print("✗ Database query test failed")
                return False
        else:
            print("✗ Database connection failed")
            return False
    except Exception as e:
        print(f"✗ Connection test error: {e}")
        return False

def get_vacation_info(config, employee_id, year=None):
    """Get vacation information for specific employee."""
    try:
        from vacation import load_vacation_data, match_vacation_users, calculate_vacation_days, get_employee_vacation_summary
        
        # Load vacation data
        vacation_data = load_vacation_data()
        if not vacation_data:
            return {'error': 'Vacation data not available'}
        
        # Match users
        user_mapping = match_vacation_users(vacation_data, config)
        if not user_mapping:
            return {'error': 'Unable to match vacation users to database'}
        
        # Calculate vacation days
        vacation_summary = calculate_vacation_days(vacation_data, user_mapping)
        if not vacation_summary:
            return {'error': 'Unable to calculate vacation data'}
        
        # Get specific employee info
        result = get_employee_vacation_summary(employee_id, vacation_summary, year)
        return result
        
    except Exception as e:
        print(f"Error getting vacation info: {e}")
        return {'error': f'Failed to get vacation info: {str(e)}'}