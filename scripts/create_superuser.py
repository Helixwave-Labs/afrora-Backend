import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.database.database import AsyncSessionLocalWrite
from app.infrastructure.models import models
from app.infrastructure.services import auth
import getpass

async def create_superuser():
    async with AsyncSessionLocalWrite() as db:
        try:
            print("--- Create Superuser ---")
            username = input("Username: ")
            email = input("Email: ")
            password = getpass.getpass("Password: ")
            confirm_password = getpass.getpass("Confirm Password: ")

            if password != confirm_password:
                print("Error: Passwords do not match.")
                return

            # Check if user already exists
            result = await db.execute(
                select(models.User).filter(
                    (models.User.email == email) | (models.User.username == username)
                )
            )
            existing_user = result.scalars().first()
            
            if existing_user:
                print(f"Error: User with email {email} or username {username} already exists.")
                return

            # Hash password and create user
            hashed_password = auth.hash_password(password)
            
            new_user = models.User(
                username=username,
                email=email,
                hashed_password=hashed_password,
                role="admin",
                is_active=True,
                otp=None,
                otp_expires_at=None
            )
            
            db.add(new_user)
            await db.commit()
            print(f"Success! Superuser '{username}' created.")

        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(create_superuser())