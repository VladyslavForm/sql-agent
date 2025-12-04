import re

def clean_sql(sql):
    """Clean and validate SQL query."""
    if not sql:
        return None
        
    # Remove markdown formatting if present
    sql = re.sub(r'^```sql\s*', '', sql, flags=re.IGNORECASE | re.MULTILINE)
    sql = re.sub(r'^```\s*', '', sql, flags=re.IGNORECASE | re.MULTILINE)
    sql = re.sub(r'\s*```$', '', sql, flags=re.MULTILINE)
    
    # Clean whitespace
    sql = sql.strip()
    
    return sql

def is_safe_query(sql):
    """Basic safety check for SQL queries."""
    if not sql:
        return False
        
    sql_upper = sql.upper().strip()
    
    # Only allow SELECT statements and WITH clauses (CTE)
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
            
    return True

def format_results(data):
    """Format query results for display."""
    if not data:
        return "No results found."
        
    if isinstance(data, list) and len(data) == 0:
        return "No results found."
        
    if isinstance(data, dict) and 'status' in data:
        return f"Operation completed: {data['status']}"
        
    return data

def print_table(data):
    """Simple table printing for query results."""
    if not data or not isinstance(data, list) or len(data) == 0:
        print("No data to display.")
        return
        
    # Get column headers
    headers = list(data[0].keys()) if data else []
    if not headers:
        print("No columns found.")
        return
        
    # Print headers
    print(" | ".join(headers))
    print("-" * (len(" | ".join(headers))))
    
    # Print rows
    for row in data[:10]:  # Limit to first 10 rows
        values = [str(row.get(header, '')) for header in headers]
        print(" | ".join(values))
        
    if len(data) > 10:
        print(f"... and {len(data) - 10} more rows")