import sys
import os
# sys.path.append(os.path.join(os.path.dirname(__file__), 'app_packages'))

from app import create_app, db
from app.models import User

app = create_app()

with app.app_context():
    if not User.query.filter_by(username='admin').first():
        print("Creating default admin user...")
        admin = User(username='admin', is_admin=True)
        admin.set_password('admin123') # 默认密码
        db.session.add(admin)
        db.session.commit()
        print("Admin user created: admin / admin123")
    else:
        print("Admin user already exists.")
