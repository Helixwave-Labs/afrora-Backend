from app.infrastructure.database.database import write_engine as engine, Base
import app.infrastructure.models.models

def init():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    print("Creating database tables if they do not exist...")
    try:
        init()
        print("Database initialization complete.")
    except Exception as e:
        print(f"Error initializing database: {e}")