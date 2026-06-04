import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.database.database import AsyncSessionLocalWrite
from app.infrastructure.models import models
from app.infrastructure.services import auth

async def main():
    async with AsyncSessionLocalWrite() as db:
        # Check if we already have a super admin
        res = await db.execute(select(models.AdminUser).filter(models.AdminUser.email == "admin@afrora.com"))
        if res.scalars().first():
            print("Admin user already exists.")
            return
        
        hashed = auth.hash_password("adminpassword123")
        admin = models.AdminUser(
            name="Afróra Super Admin",
            email="admin@afrora.com",
            password_hash=hashed,
            role=models.AdminRole.super_admin
        )
        db.add(admin)
        await db.commit()
        print("Super Admin created: admin@afrora.com / adminpassword123")

if __name__ == "__main__":
    asyncio.run(main())
