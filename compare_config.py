from app import create_app, db
from app.utils import import_servers_from_excel
import os

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # 确保数据库表存在
        
        # 导入服务器配置
        excel_path = os.path.join(os.path.dirname(__file__), 'hosts.xlsx')
        if os.path.exists(excel_path):
            import_servers_from_excel(excel_path)
            
    app.run(debug=True, host='0.0.0.0', port=5000)
