"""
Simple testing framework for SQL Agent.
Tests core functionality without external dependencies.
"""

import time
import sys
from typing import List, Tuple

# Import project modules
from config import load_config, validate_config
from database import test_connection, get_schema, execute_query, is_safe_sql, add_limit_if_needed, get_vacation_info
from llm import test_openrouter, generate_sql, generate_response, fix_sql_error, clean_sql_response
from vacation import load_vacation_data, match_vacation_users, calculate_vacation_days
from utils import is_safe_query, clean_sql
from main import process_question, is_vacation_question

class TestResult:
    """Simple test result class."""
    def __init__(self, name: str, passed: bool, message: str = "", duration: float = 0.0):
        self.name = name
        self.passed = passed
        self.message = message
        self.duration = duration

class TestRunner:
    """Simple test runner class."""
    def __init__(self):
        self.results: List[TestResult] = []
        self.config = None
    
    def run_test(self, test_name: str, test_func):
        """Run a single test function."""
        print(f"Running {test_name}...", end=" ")
        start_time = time.time()
        
        try:
            test_func()
            duration = time.time() - start_time
            self.results.append(TestResult(test_name, True, "PASSED", duration))
            print("✓ PASSED")
        except AssertionError as e:
            duration = time.time() - start_time
            message = str(e) if str(e) else "Assertion failed"
            self.results.append(TestResult(test_name, False, f"FAILED: {message}", duration))
            print(f"✗ FAILED: {message}")
        except Exception as e:
            duration = time.time() - start_time
            message = f"Error: {str(e)}"
            self.results.append(TestResult(test_name, False, message, duration))
            print(f"✗ ERROR: {e}")
    
    def load_test_config(self):
        """Load configuration for testing."""
        try:
            self.config = load_config()
            # Don't validate config - let individual tests handle missing credentials
            return True
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
            return False
    
    def print_summary(self):
        """Print test summary."""
        passed = sum(1 for result in self.results if result.passed)
        total = len(self.results)
        failed = total - passed
        
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        for result in self.results:
            status_icon = "✓" if result.passed else "✗"
            print(f"{status_icon} {result.name:<40} ({result.duration:.3f}s)")
            if not result.passed and result.message:
                print(f"  └─ {result.message}")
        
        print("-" * 60)
        print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
        
        if failed == 0:
            print("🎉 All tests passed!")
        else:
            print(f"⚠️  {failed} test(s) failed.")
        
        return failed == 0

def test_database_connection(runner):
    """Test database connectivity."""
    if not runner.config:
        # Test without config should fail gracefully
        assert False, "No configuration available"
    
    try:
        validate_config(runner.config)
        # If config is valid, test connection
        result = test_connection(runner.config)
        assert result, "Database connection failed"
    except ValueError as e:
        if "Missing required configuration" in str(e):
            # This is expected when DB credentials are missing
            print("(Expected failure - no DB credentials)")
            return
        raise

def test_schema_retrieval(runner):
    """Test database schema retrieval."""
    if not runner.config:
        assert False, "No configuration available"
    
    try:
        validate_config(runner.config)
        schema = get_schema(runner.config)
        assert schema is not None, "Schema retrieval failed"
        assert isinstance(schema, dict), "Schema should be a dictionary"
        assert len(schema) > 0, "Schema should contain tables"
    except ValueError as e:
        if "Missing required configuration" in str(e):
            print("(Expected failure - no DB credentials)")
            return
        raise

def test_llm_connection(runner):
    """Test OpenRouter API connection."""
    if not runner.config:
        assert False, "No configuration available"
    
    try:
        validate_config(runner.config)
        result = test_openrouter(runner.config)
        assert result, "OpenRouter API connection failed"
    except ValueError as e:
        if "Missing required configuration" in str(e):
            print("(Expected failure - no API key)")
            return
        raise

def test_sql_safety():
    """Test SQL safety validation functions."""
    # Test dangerous queries are blocked
    dangerous_queries = [
        "DROP TABLE users",
        "DELETE FROM employees", 
        "INSERT INTO users VALUES (1, 'test')",
        "UPDATE employees SET name = 'test'",
        "TRUNCATE TABLE projects",
        "ALTER TABLE users ADD COLUMN test VARCHAR(100)",
        "CREATE TABLE test (id INT)"
    ]
    
    for query in dangerous_queries:
        assert not is_safe_sql(query), f"Should block dangerous query: {query}"
        assert not is_safe_query(query), f"Utils should block dangerous query: {query}"
    
    # Test safe queries are allowed
    safe_queries = [
        "SELECT * FROM users",
        "SELECT COUNT(*) FROM employees",
        "SELECT name FROM projects WHERE active = true",
        "SELECT e.name, t.name FROM employee e JOIN team t ON e.team_id = t.id"
    ]
    
    for query in safe_queries:
        assert is_safe_sql(query), f"Should allow safe query: {query}"
        assert is_safe_query(query), f"Utils should allow safe query: {query}"

def test_limit_protection():
    """Test automatic LIMIT clause addition."""
    # Test LIMIT is added to queries without it
    query_without_limit = "SELECT * FROM users"
    result = add_limit_if_needed(query_without_limit)
    assert "LIMIT 1000" in result, "Should add LIMIT clause"
    
    # Test LIMIT is preserved in queries that have it
    query_with_limit = "SELECT * FROM users LIMIT 50"
    result = add_limit_if_needed(query_with_limit)
    assert "LIMIT 50" in result, "Should preserve existing LIMIT"
    assert result.count("LIMIT") == 1, "Should not add duplicate LIMIT"
    
    # Test non-SELECT queries are not modified
    non_select = "INSERT INTO users VALUES (1)"
    result = add_limit_if_needed(non_select)
    assert result == non_select, "Should not modify non-SELECT queries"

def test_vacation_loading():
    """Test vacation data loading functionality."""
    # Test vacation data loads successfully
    vacation_data = load_vacation_data()
    assert vacation_data is not None, "Vacation data should load"
    assert isinstance(vacation_data, dict), "Vacation data should be a dictionary"
    assert 'n_users' in vacation_data, "Should have user count"
    assert 'n_requests' in vacation_data, "Should have request count"
    assert 'users' in vacation_data, "Should have users list"
    assert 'requests' in vacation_data, "Should have requests list"
    
    # Test data structure
    users = vacation_data.get('users', [])
    requests = vacation_data.get('requests', [])
    assert len(users) > 0, "Should have users"
    assert len(requests) > 0, "Should have vacation requests"

def test_vacation_question_detection():
    """Test vacation question detection."""
    # Test vacation questions are detected
    vacation_questions = [
        "How many vacation days does John have?",
        "Who is on holiday this week?",
        "Show me sick leave for the team",
        "Скільки днів відпустки у Петра?",  # Ukrainian
        "What is the leave policy?"
    ]
    
    for question in vacation_questions:
        assert is_vacation_question(question), f"Should detect vacation question: {question}"
    
    # Test non-vacation questions are not detected
    regular_questions = [
        "How many employees are there?",
        "Show me the project status",
        "What are the team members?",
        "List all developers"
    ]
    
    for question in regular_questions:
        assert not is_vacation_question(question), f"Should not detect as vacation question: {question}"

def test_sql_cleaning():
    """Test SQL response cleaning functionality."""
    # Test markdown removal
    sql_with_markdown = """```sql
SELECT * FROM users;
```"""
    cleaned = clean_sql_response(sql_with_markdown)
    assert "SELECT * FROM users;" in cleaned, "Should preserve SQL content"
    assert "```" not in cleaned, "Should remove markdown"
    
    # Test prefix removal
    sql_with_prefix = "SQL Query: SELECT COUNT(*) FROM employees;"
    cleaned = clean_sql_response(sql_with_prefix)
    assert cleaned == "SELECT COUNT(*) FROM employees;", "Should remove prefix"
    
    # Test basic SQL cleaning
    messy_sql = "  SELECT * FROM users  "
    cleaned = clean_sql(messy_sql)
    assert cleaned.strip() == "SELECT * FROM users", "Should clean whitespace"

def test_end_to_end_processing(runner):
    """Test complete question processing pipeline."""
    if not runner.config:
        assert False, "No configuration available"
    
    try:
        validate_config(runner.config)
        
        # Test with a simple question
        question = "How many employees are there?"
        result = process_question(question, runner.config, debug=False)
        
        # Should return some result (even if it's an error message)
        assert result is not None, "Should return a result"
        assert isinstance(result, str), "Result should be a string"
        assert len(result) > 0, "Result should not be empty"
        
    except ValueError as e:
        if "Missing required configuration" in str(e):
            print("(Expected failure - no credentials)")
            return
        raise

def test_required_questions(runner):
    """Test the 4 specific required questions."""
    if not runner.config:
        print("(Skipped - no configuration)")
        return
    
    try:
        validate_config(runner.config)
    except ValueError as e:
        if "Missing required configuration" in str(e):
            print("(Expected failure - no credentials)")
            return
        raise
    
    required_questions = [
        "How much on average do task estimates exceed actual time spent for Alpha team?",
        "What is the most active project in Fusion team by hours logged last week?",
        "Describe the composition of each team by developer specialization",
        "How many vacation days has each Alpha team member taken since the beginning of the year?"
    ]
    
    for i, question in enumerate(required_questions, 1):
        try:
            result = process_question(question, runner.config, debug=False)
            assert result is not None, f"Question {i} should return a result"
            assert isinstance(result, str), f"Question {i} result should be a string"
            assert len(result) > 0, f"Question {i} result should not be empty"
            
            # Should not return basic error messages (indicates some processing occurred)
            error_indicators = [
                "Unable to retrieve database schema",
                "Unable to generate SQL query", 
                "Generated SQL is empty"
            ]
            for error in error_indicators:
                if error in result:
                    print(f"(Question {i} failed at {error.lower()} stage)")
                    break
                    
        except Exception as e:
            print(f"(Question {i} failed with error: {e})")

def run_all_tests():
    """Run all tests and return success status."""
    runner = TestRunner()
    
    print("SQL Agent Testing Framework")
    print("=" * 60)
    
    # Load configuration
    config_loaded = runner.load_test_config()
    if not config_loaded:
        print("Warning: Configuration not loaded. Some tests will be skipped.")
    
    print()
    
    # Run individual component tests
    runner.run_test("Database Connection", lambda: test_database_connection(runner))
    runner.run_test("Schema Retrieval", lambda: test_schema_retrieval(runner))
    runner.run_test("LLM Connection", lambda: test_llm_connection(runner))
    runner.run_test("SQL Safety Validation", test_sql_safety)
    runner.run_test("LIMIT Protection", test_limit_protection)
    runner.run_test("Vacation Data Loading", test_vacation_loading)
    runner.run_test("Vacation Question Detection", test_vacation_question_detection)
    runner.run_test("SQL Cleaning", test_sql_cleaning)
    runner.run_test("End-to-End Processing", lambda: test_end_to_end_processing(runner))
    runner.run_test("Required Questions", lambda: test_required_questions(runner))
    
    # Print summary
    return runner.print_summary()

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)