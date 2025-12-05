import requests
import json

# Enhanced prompt templates with Ukrainian support
SQL_GENERATION_TEMPLATE = """Given this PostgreSQL database schema:
{schema}

Generate a SQL query to answer this question: {question}

CRITICAL REQUIREMENTS:
- Use only SELECT statements (no INSERT/UPDATE/DELETE/DROP)
- ⚠️ CRITICAL: ALL time values are in MICROSECONDS - ALWAYS divide by 3600000000.0 (NOT 3600) ⚠️
- WRONG: time_spent / 3600.0 
- CORRECT: time_spent / 3600000000.0
- Today's date: {current_date}
- Available data range: 2022-01-01 to 2025-11-21 (latest data cutoff)

TEMPORAL REASONING:
- Data ends on 2025-11-21, so use the most recent available period for "recent" queries
- "last week/previous week" = most recent 7-day period with data (2025-11-14 to 2025-11-21)
- "recent/lately" = last 30 days of available data (2025-10-22 to 2025-11-21)
- "this month" = November 2025 (current month of latest data)
- "since beginning of year" = January 1st 2025 to latest available
- Prioritize finding actual data over perfect date alignment

PRACTICAL DATE RANGES (use these for better results):
```sql
-- Recent week activity (use latest available 7 days)
WHERE date_column >= '2025-11-14' AND date_column <= '2025-11-21'

-- Recent activity (last 30 days of data)  
WHERE date_column >= '2025-10-22' AND date_column <= '2025-11-21'

-- Recent month activity
WHERE date_column >= '2025-11-01' AND date_column <= '2025-11-21'

-- Since beginning of year
WHERE date_column >= '2025-01-01'

-- Alternative: Use relative dates but constrain to available data
WHERE date_column >= GREATEST('2025-11-14', DATE_TRUNC('week', '2025-11-21'::date - INTERVAL '1 week'))
AND date_column <= '2025-11-21'
```

LANGUAGE MAPPINGS (Ukrainian → English):
- команда/team → team.name
- проект/project → project.name  
- розробник/developer → developer/employee
- відпуск/vacation → vacation data
- спеціалізація/specialization → developer.specialization
- години/hours → time_spent/time_estimate (convert from microseconds)

SCHEMA RELATIONSHIPS:
- employee.team_id → team.team_id
- employee.clickup_id → developer.clickup_id (for specializations)
- task_employee links tasks to employees
- project_employee links projects to employees

QUERY PATTERNS:

For team activity/project hours (активність команди):
```sql
-- Most active project by hours in team (recent week)
SELECT 
  p.name as project_name,
  SUM(t.time_spent) / 3600000000.0 as total_hours
FROM project p
JOIN task t ON t.clickup_id = p.clickup_id
JOIN task_employee te ON t.task_id = te.task_id
JOIN employee e ON te.employee_id = e.employee_id
JOIN team tm ON e.team_id = tm.team_id
WHERE tm.name = 'Fusion' 
  AND t.date_updated >= '2025-11-14' 
  AND t.date_updated <= '2025-11-21'
  AND t.time_spent IS NOT NULL
GROUP BY p.project_id, p.name
ORDER BY total_hours DESC
LIMIT 1;
```

For team composition by specialization (композиція команди):
```sql
-- Team composition with developer specializations
SELECT 
  t.name as team_name,
  COALESCE(d.specialization, 'Unknown') as specialization,
  COUNT(DISTINCT e.employee_id) as developer_count
FROM team t
JOIN employee e ON t.team_id = e.team_id
LEFT JOIN developer d ON e.clickup_id = d.clickup_id
GROUP BY t.name, COALESCE(d.specialization, 'Unknown')
ORDER BY t.name, developer_count DESC;
```

For vacation queries (відпуск):
```sql
-- Alpha team vacation days since New Year
SELECT 
  e.name as employee_name,
  e.employee_id,
  'Use vacation.py data integration' as vacation_note
FROM employee e
JOIN team t ON e.team_id = t.team_id
WHERE t.name = 'Alpha';
```

IMPORTANT:
- Always convert microseconds to hours using "/ 3600000000.0"
- Use LEFT JOINs when data might be missing
- Handle NULL values with COALESCE
- For vacation queries, note that external vacation data integration is needed
- Return only the SQL query, no explanation

SQL Query:"""

RESPONSE_GENERATION_TEMPLATE = """Question: {question}

Query Results:
{data}

Please provide a clear, helpful answer to the question based on the query results. 
{language_instruction}

Answer:"""

SQL_ERROR_CORRECTION_TEMPLATE = """Database Schema:
{schema}

Failed SQL Query:
{sql}

Error Message:
{error}

Please fix the SQL query to resolve this error. 

CRITICAL: Time values are in MICROSECONDS - always convert to hours by dividing by 3600000000.0 (not 3600)

Return only the corrected SQL query, no explanation.

Corrected SQL:"""

def call_openrouter(config, messages):
    """Make API call to OpenRouter."""
    try:
        headers = {
            'Authorization': f"Bearer {config['openrouter_api_key']}",
            'Content-Type': 'application/json',
            'HTTP-Referer': 'http://localhost',
            'X-Title': 'SQL Agent'
        }
        
        data = {
            'model': config.get('llm_model', 'anthropic/claude-3.5-sonnet'),
            'messages': messages,
            'max_tokens': config.get('max_response_length', 2000),
            'temperature': 0.1
        }
        
        timeout = config.get('llm_timeout', 30)
        
        if config.get('debug'):
            print(f"Making OpenRouter API call with model: {data['model']}")
        
        response = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers=headers,
            json=data,
            timeout=timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            if config.get('debug'):
                print(f"OpenRouter API success: {len(result.get('choices', []))} choices")
            return result
        elif response.status_code == 401:
            print("OpenRouter API error: Invalid API key")
            return {'error': 'Invalid API key'}
        elif response.status_code == 429:
            print("OpenRouter API error: Rate limit exceeded")
            return {'error': 'Rate limit exceeded'}
        else:
            print(f"OpenRouter API error: HTTP {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error details: {error_data}")
            except:
                pass
            return {'error': f'HTTP {response.status_code}'}
            
    except requests.exceptions.Timeout:
        print(f"OpenRouter API timeout after {timeout} seconds")
        return {'error': 'Request timeout'}
    except requests.exceptions.ConnectionError:
        print("OpenRouter API connection error")
        return {'error': 'Connection error'}
    except Exception as e:
        print(f"OpenRouter call error: {e}")
        return {'error': str(e)}

def generate_sql(config, question, schema):
    """Generate SQL query from natural language question."""
    from database import format_schema_for_llm
    from datetime import date
    
    schema_text = format_schema_for_llm(schema)
    current_date = date.today().strftime('%Y-%m-%d')
    
    prompt = SQL_GENERATION_TEMPLATE.format(
        schema=schema_text,
        question=question,
        current_date=current_date
    )
    
    messages = [{'role': 'user', 'content': prompt}]
    
    try:
        response = call_openrouter(config, messages)
        
        if response and 'error' in response:
            print(f"SQL generation failed: {response['error']}")
            return None
            
        if response and 'choices' in response and response['choices']:
            sql = response['choices'][0]['message']['content'].strip()
            
            # Clean up the response - remove markdown formatting
            sql = clean_sql_response(sql)
            
            if config.get('debug'):
                print(f"Generated SQL: {sql}")
            
            return sql
            
        return None
        
    except Exception as e:
        print(f"SQL generation error: {e}")
        return None

def clean_sql_response(sql):
    """Clean SQL response from LLM."""
    if not sql:
        return sql
    
    # Remove markdown code blocks
    lines = sql.split('\n')
    cleaned_lines = []
    in_code_block = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        # Include lines when we're in a code block OR when we have content outside code blocks
        if (in_code_block and stripped) or (not in_code_block and stripped):
            cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines).strip()
    
    # Remove common prefixes
    prefixes = ['SQL Query:', 'Query:', 'SQL:']
    for prefix in prefixes:
        if result.startswith(prefix):
            result = result[len(prefix):].strip()
    
    return result

def format_and_enhance_data(data, question):
    """Format and enhance data with business context."""
    if not data or isinstance(data, dict) and 'error' in data:
        return data
    
    # Convert time values and add context
    enhanced_data = []
    for row in data:
        enhanced_row = {}
        for key, value in row.items():
            # Convert large numbers that look like time in microseconds to hours
            if isinstance(value, (int, float)) and value > 3600000 and ('time' in key.lower() or 'spent' in key.lower() or 'hours' in key.lower()):
                hours = value / 3600000000.0
                enhanced_row[key] = f"{hours:.1f} hours"
            # Format other large numbers
            elif isinstance(value, (int, float)) and value > 1000000:
                enhanced_row[key] = f"{value:,}"
            else:
                enhanced_row[key] = value
        enhanced_data.append(enhanced_row)
    
    return enhanced_data

def generate_response(config, question, data):
    """Generate natural language response from query results."""
    # Handle empty or error results
    if not data:
        return "No results found for your question."
    
    if isinstance(data, dict) and 'error' in data:
        return f"There was an error processing your question: {data['error']}"
    
    # Enhance data with formatting and context
    data = format_and_enhance_data(data, question)
    
    # Determine language instruction
    language = config.get('response_language', 'auto')
    if language == 'auto':
        # Simple detection based on question content
        if any(char in question for char in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'):
            language_instruction = "Please respond in Ukrainian."
        else:
            language_instruction = "Please respond in English."
    elif language == 'ukrainian':
        language_instruction = "Please respond in Ukrainian."
    elif language == 'english':
        language_instruction = "Please respond in English."
    else:
        language_instruction = ""
    
    # Format data for prompt
    if isinstance(data, list) and len(data) > 10:
        # Truncate long results
        data_text = json.dumps(data[:10], indent=2, ensure_ascii=False)
        data_text += f"\n... and {len(data) - 10} more rows"
    else:
        data_text = json.dumps(data, indent=2, ensure_ascii=False)
    
    prompt = RESPONSE_GENERATION_TEMPLATE.format(
        question=question,
        data=data_text,
        language_instruction=language_instruction
    )
    
    messages = [{'role': 'user', 'content': prompt}]
    
    try:
        response = call_openrouter(config, messages)
        
        if response and 'error' in response:
            print(f"Response generation failed: {response['error']}")
            return "I encountered an error while generating a response to your question."
            
        if response and 'choices' in response and response['choices']:
            result = response['choices'][0]['message']['content'].strip()
            
            # Remove common prefixes
            prefixes = ['Answer:', 'Response:']
            for prefix in prefixes:
                if result.startswith(prefix):
                    result = result[len(prefix):].strip()
            
            if config.get('debug'):
                print(f"Generated response length: {len(result)}")
            
            return result
            
        return "I was unable to generate a response to your question."
        
    except Exception as e:
        print(f"Response generation error: {e}")
        return "I encountered an error while processing your question."


def fix_sql_error(config, sql, error_message, schema):
    """Fix SQL query based on error message."""
    from database import format_schema_for_llm
    schema_text = format_schema_for_llm(schema)
    
    prompt = SQL_ERROR_CORRECTION_TEMPLATE.format(
        schema=schema_text,
        sql=sql,
        error=error_message
    )
    
    messages = [{'role': 'user', 'content': prompt}]
    
    try:
        response = call_openrouter(config, messages)
        
        if response and 'error' in response:
            print(f"SQL error correction failed: {response['error']}")
            return None
            
        if response and 'choices' in response and response['choices']:
            fixed_sql = response['choices'][0]['message']['content'].strip()
            
            # Clean up the response
            fixed_sql = clean_sql_response(fixed_sql)
            
            if config.get('debug'):
                print(f"Original SQL: {sql}")
                print(f"Error: {error_message}")
                print(f"Fixed SQL: {fixed_sql}")
            
            return fixed_sql
            
        return None
        
    except Exception as e:
        print(f"SQL error correction error: {e}")
        return None

def test_openrouter(config):
    """Test OpenRouter API connection."""
    try:
        messages = [{'role': 'user', 'content': 'Say "test successful"'}]
        response = call_openrouter(config, messages)
        
        if response and 'choices' in response:
            content = response['choices'][0]['message']['content']
            return 'test successful' in content.lower()
        return False
        
    except Exception as e:
        print(f"OpenRouter test error: {e}")
        return False