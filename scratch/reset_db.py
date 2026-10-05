import sqlite3
from app.database import engine, Base
from app.models import Project

def reset_database():
    conn = sqlite3.connect('test_case_generator.db')
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    
    print(f"Found tables: {tables}")
    for table in tables:
        if not table.startswith('sqlite_'):
            cursor.execute(f"DELETE FROM {table};")
            print(f"Cleared table: {table}")
            
    conn.commit()
    conn.close()
    
    # Re-create tables if missing and insert default project
    Base.metadata.create_all(bind=engine)
    
    conn = sqlite3.connect('test_case_generator.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO projects (id, name, description, created_at) VALUES ('default', 'Fresh Start Project', 'Clean workspace for new testing session', CURRENT_TIMESTAMP);")
    conn.commit()
    conn.close()
    
    print("Database reset completed successfully! Ready for fresh start.")

if __name__ == "__main__":
    reset_database()
