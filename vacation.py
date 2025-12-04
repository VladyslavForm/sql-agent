import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

def load_vacation_data(file_path: str = "vacation_requests.json") -> Optional[Dict[str, Any]]:
    """Load vacation data from JSON file."""
    try:
        print(f"Loading vacation data from {file_path}...")
        
        if not os.path.exists(file_path):
            print(f"Warning: Vacation file not found: {file_path}")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        
        if not isinstance(data, dict):
            print("Error: Invalid vacation data format")
            return None
        
        users_count = data.get('n_users', 0)
        requests_count = data.get('n_requests', 0)
        users = data.get('users', [])
        requests = data.get('requests', [])
        
        print(f"✓ Loaded {users_count} users and {requests_count} vacation requests")
        print(f"✓ Found {len(users)} user records and {len(requests)} request records")
        
        return data
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in vacation file: {e}")
        return None
    except Exception as e:
        print(f"Error loading vacation data: {e}")
        return None

def match_vacation_users(vacation_data: Dict[str, Any], config: Dict[str, Any]) -> Dict[int, int]:
    """Match ClickUp user IDs to database employee IDs."""
    if not vacation_data:
        print("No vacation data to match")
        return {}
    
    try:
        from database import execute_query
        
        print("Matching ClickUp users to database employees...")
        
        # Get developers from database
        dev_query = "SELECT id, clickup_id, name FROM developer WHERE clickup_id IS NOT NULL"
        db_developers = execute_query(config, dev_query)
        
        if not db_developers:
            print("Warning: No developers with ClickUp IDs found in database")
            return {}
        
        # Create mapping from ClickUp ID to employee ID
        user_mapping = {}
        vacation_users = vacation_data.get('users', [])
        
        for db_dev in db_developers:
            clickup_id = db_dev.get('clickup_id')
            employee_id = db_dev.get('id')
            name = db_dev.get('name', 'Unknown')
            
            if clickup_id and employee_id:
                user_mapping[clickup_id] = employee_id
                print(f"✓ Mapped ClickUp ID {clickup_id} to employee {employee_id} ({name})")
        
        print(f"✓ Successfully mapped {len(user_mapping)} users")
        return user_mapping
        
    except Exception as e:
        print(f"Error matching vacation users: {e}")
        return {}

def calculate_vacation_days(vacation_data: Dict[str, Any], user_mapping: Dict[int, int]) -> Dict[int, Dict[str, Any]]:
    """Calculate vacation days for each employee."""
    if not vacation_data or not user_mapping:
        print("No data available for vacation calculations")
        return {}
    
    try:
        print("Calculating vacation days...")
        
        requests = vacation_data.get('requests', [])
        vacation_summary = {}
        
        for request in requests:
            requester_clickup_id = request.get('requester')
            start_date_str = request.get('start_date')
            due_date_str = request.get('due_date')
            vacation_type = request.get('type', 'Unknown')
            status = request.get('status', 'Unknown')
            
            # Skip if user not in mapping
            if requester_clickup_id not in user_mapping:
                continue
            
            employee_id = user_mapping[requester_clickup_id]
            
            # Parse dates
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                
                # Calculate days
                days = (due_date - start_date).days + 1  # +1 to include both start and end dates
                year = start_date.year
                
                # Initialize employee summary if not exists
                if employee_id not in vacation_summary:
                    vacation_summary[employee_id] = {
                        'total_days': 0,
                        'by_year': {},
                        'by_type': {},
                        'by_status': {}
                    }
                
                # Update totals
                vacation_summary[employee_id]['total_days'] += days
                
                # Update by year
                if year not in vacation_summary[employee_id]['by_year']:
                    vacation_summary[employee_id]['by_year'][year] = 0
                vacation_summary[employee_id]['by_year'][year] += days
                
                # Update by type
                if vacation_type not in vacation_summary[employee_id]['by_type']:
                    vacation_summary[employee_id]['by_type'][vacation_type] = 0
                vacation_summary[employee_id]['by_type'][vacation_type] += days
                
                # Update by status
                if status not in vacation_summary[employee_id]['by_status']:
                    vacation_summary[employee_id]['by_status'][status] = 0
                vacation_summary[employee_id]['by_status'][status] += days
                
            except (ValueError, TypeError) as e:
                print(f"Warning: Invalid date format in request {request.get('id')}: {e}")
                continue
        
        print(f"✓ Calculated vacation data for {len(vacation_summary)} employees")
        
        # Print summary
        for emp_id, summary in vacation_summary.items():
            total = summary['total_days']
            years = list(summary['by_year'].keys())
            print(f"  Employee {emp_id}: {total} total days across years {years}")
        
        return vacation_summary
        
    except Exception as e:
        print(f"Error calculating vacation days: {e}")
        return {}

def get_employee_vacation_summary(employee_id: int, vacation_summary: Dict[int, Dict[str, Any]], year: Optional[int] = None) -> Dict[str, Any]:
    """Get vacation summary for specific employee."""
    if employee_id not in vacation_summary:
        return {
            'employee_id': employee_id,
            'total_days': 0,
            'message': 'No vacation data found for this employee'
        }
    
    summary = vacation_summary[employee_id]
    
    if year:
        year_days = summary['by_year'].get(year, 0)
        return {
            'employee_id': employee_id,
            'year': year,
            'days': year_days,
            'by_type': {k: v for k, v in summary['by_type'].items() if k},
            'by_status': {k: v for k, v in summary['by_status'].items() if k}
        }
    else:
        return {
            'employee_id': employee_id,
            'total_days': summary['total_days'],
            'by_year': summary['by_year'],
            'by_type': summary['by_type'],
            'by_status': summary['by_status']
        }

def format_vacation_info(vacation_info: Dict[str, Any]) -> str:
    """Format vacation information for display."""
    if vacation_info.get('message'):
        return vacation_info['message']
    
    employee_id = vacation_info.get('employee_id')
    
    if 'year' in vacation_info:
        year = vacation_info['year']
        days = vacation_info['days']
        result = f"Employee {employee_id} vacation in {year}: {days} days"
    else:
        total_days = vacation_info.get('total_days', 0)
        result = f"Employee {employee_id} total vacation: {total_days} days"
        
        by_year = vacation_info.get('by_year', {})
        if by_year:
            year_breakdown = ", ".join([f"{year}: {days} days" for year, days in sorted(by_year.items())])
            result += f"\nBy year: {year_breakdown}"
    
    return result