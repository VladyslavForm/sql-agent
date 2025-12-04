import requests
import json

# Simple prompt templates
SQL_GENERATION_TEMPLATE = """Given this PostgreSQL database schema:
{schema}

Generate a SQL query to answer this question: {question}

CRITICAL REQUIREMENTS:
- Use only SELECT statements (no INSERT/UPDATE/DELETE/DROP)
- ALL time values are in SECONDS - always convert to hours by dividing by 3600
- Data is only available until 2025-11-21, adjust date ranges accordingly
- For "recent" queries, use dates like '2025-11-01' to '2025-11-21'

QUERY PATTERNS:

For team activity queries:
```sql
-- Find most active project in team by hours
SELECT p.name, (p.time_spent / 3600.0) as hours_spent
FROM project p 
WHERE p.team = 'TeamName' 
  AND p.date_updated >= '2025-11-01'
ORDER BY p.time_spent DESC 
LIMIT 1;
```

For team composition queries:
```sql  
-- Get team composition by role
SELECT t.name as team_name, e.position, COUNT(*) as count
FROM team t 
JOIN employee e ON t.team_id = e.team_id
GROUP BY t.name, e.position
ORDER BY t.name, count DESC;
```

For time estimate vs actual analysis:
```sql
-- Compare estimates vs actual time for team
SELECT 
  AVG((t.time_estimate - t.time_spent) / 3600.0) as avg_hours_difference
FROM task t
JOIN task_employee te ON t.task_id = te.task_id  
JOIN employee e ON te.employee_id = e.employee_id
JOIN team tm ON e.team_id = tm.team_id
WHERE tm.name = 'TeamName'
  AND t.time_estimate IS NOT NULL 
  AND t.time_spent IS NOT NULL;
```

IMPORTANT:
- Always convert seconds to hours using "/ 3600.0" 
- Use proper JOINs to connect tables
- Filter by realistic date ranges (2022-2025)
- Include meaningful column aliases
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

Please fix the SQL query to resolve this error. Return only the corrected SQL query, no explanation.

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
    schema_text = format_schema_for_llm(schema)
    
    prompt = SQL_GENERATION_TEMPLATE.format(
        schema=schema_text,
        question=question
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
            # Convert large numbers that look like time in seconds to hours
            if isinstance(value, (int, float)) and value > 3600 and ('time' in key.lower() or 'spent' in key.lower()):
                hours = value / 3600.0
                enhanced_row[key] = f"{value} seconds ({hours:.1f} hours)"
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