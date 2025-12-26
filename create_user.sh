#!/bin/bash
# Script to create a test user in Docker

docker-compose exec backend python -c "
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.models import User

db = SessionLocal()
try:
    # Check if user exists
    existing = db.query(User).filter(User.username == 'admin').first()
    if existing:
        print('User admin already exists')
    else:
        user = User(
            email='admin@loadopt.com',
            username='admin',
            full_name='Admin User',
            hashed_password=get_password_hash('admin123'),
            is_active=True,
            is_superuser=True
        )
        db.add(user)
        db.commit()
        print('✓ User created successfully!')
        print('  Username: admin')
        print('  Password: admin123')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
finally:
    db.close()
"
