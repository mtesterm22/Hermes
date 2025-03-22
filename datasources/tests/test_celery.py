# Create a new test_celery.py file
from datasources.tasks import add

def test_simple_task():
    """Send a simple test task to Celery"""
    # Execute the task
    result = add.delay(4, 4)
    
    # Wait for the result (with timeout)
    task_result = result.get(timeout=5)
    
    # Print result for debugging
    print(f"Task ID: {result.id}")
    print(f"Task result: {task_result}")
    
    return task_result == 8

if __name__ == "__main__":
    success = test_simple_task()
    print(f"Test successful: {success}")