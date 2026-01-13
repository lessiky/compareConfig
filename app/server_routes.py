from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.models import Server, BusinessSystem
from app import db
from app.utils import encrypt_password

bp = Blueprint('server', __name__)

@bp.before_request
@login_required
def require_login():
    pass

@bp.route('/servers')
def list_servers():
    if current_user.is_admin:
        servers = Server.query.all()
        systems = BusinessSystem.query.all()
    else:
        # 普通用户只能看到授权业务系统的服务器
        system_ids = [sys.id for sys in current_user.authorized_systems]
        servers = Server.query.filter(Server.business_system_id.in_(system_ids)).all()
        systems = current_user.authorized_systems
        
    return render_template('server/list.html', servers=servers, systems=systems)

@bp.route('/servers/add', methods=['POST'])
def add_server():
    name = request.form.get('name')
    ip = request.form.get('ip')
    username = request.form.get('username')
    password = request.form.get('password')
    port = request.form.get('port', 22)
    os_type = request.form.get('os_type', 'Linux')
    business_system_id = request.form.get('business_system_id')
    
    # 权限检查
    if not current_user.is_admin:
        if not business_system_id or int(business_system_id) not in [sys.id for sys in current_user.authorized_systems]:
             flash('无权在该业务系统下添加服务器', 'danger')
             return redirect(url_for('server.list_servers'))
             
    server = Server(
        name=name, ip=ip, username=username, password=encrypt_password(password), 
        port=port, os_type=os_type, business_system_id=business_system_id
    )
    db.session.add(server)
    db.session.commit()
    flash('服务器添加成功', 'success')
    return redirect(url_for('server.list_servers'))

@bp.route('/servers/edit/<int:id>', methods=['POST'])
def edit_server(id):
    server = Server.query.get_or_404(id)
    
    # 权限检查
    if not current_user.is_admin:
        if server.business_system_id not in [sys.id for sys in current_user.authorized_systems]:
            abort(403)
            
    server.name = request.form.get('name')
    server.ip = request.form.get('ip')
    server.username = request.form.get('username')
    
    password = request.form.get('password')
    if password: # 只有当用户输入新密码时才更新
        server.password = encrypt_password(password)
        
    server.port = request.form.get('port')
    server.os_type = request.form.get('os_type')
    new_sys_id = request.form.get('business_system_id')
    
    # 检查是否修改到了无权的业务系统
    if not current_user.is_admin:
         if int(new_sys_id) not in [sys.id for sys in current_user.authorized_systems]:
             flash('无权转移到该业务系统', 'danger')
             return redirect(url_for('server.list_servers'))
             
    server.business_system_id = new_sys_id
    
    db.session.commit()
    flash('服务器更新成功', 'success')
    return redirect(url_for('server.list_servers'))

@bp.route('/servers/delete/<int:id>')
def delete_server(id):
    server = Server.query.get_or_404(id)
    
    if not current_user.is_admin:
        if server.business_system_id not in [sys.id for sys in current_user.authorized_systems]:
            abort(403)
            
    db.session.delete(server)
    db.session.commit()
    flash('服务器删除成功', 'success')
    return redirect(url_for('server.list_servers'))
