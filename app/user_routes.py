from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.models import User, BusinessSystem
from app import db

bp = Blueprint('user', __name__)

@bp.before_request
@login_required
def require_admin():
    if not current_user.is_admin:
        abort(403)

@bp.route('/users')
def list_users():
    users = User.query.all()
    systems = BusinessSystem.query.all()
    return render_template('user/list.html', users=users, systems=systems)

@bp.route('/users/add', methods=['POST'])
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    is_admin = request.form.get('is_admin') == 'on'
    system_ids = request.form.getlist('system_ids')
    
    if User.query.filter_by(username=username).first():
        flash('用户名已存在', 'danger')
        return redirect(url_for('user.list_users'))
        
    user = User(username=username, is_admin=is_admin)
    user.set_password(password)
    
    # 设置授权系统
    if system_ids:
        systems = BusinessSystem.query.filter(BusinessSystem.id.in_(system_ids)).all()
        user.authorized_systems = systems
        
    db.session.add(user)
    db.session.commit()
    flash('用户添加成功', 'success')
    return redirect(url_for('user.list_users'))

@bp.route('/users/edit/<int:id>', methods=['POST'])
def edit_user(id):
    user = User.query.get_or_404(id)
    
    # 只能改其他人的，或者改自己的非敏感信息（这里简化处理）
    
    username = request.form.get('username')
    password = request.form.get('password')
    is_admin = request.form.get('is_admin') == 'on'
    is_active = request.form.get('is_active') == 'on'
    system_ids = request.form.getlist('system_ids')
    
    user.username = username
    user.is_admin = is_admin
    user.is_active = is_active
    
    if password:
        user.set_password(password)
        
    # 更新授权系统
    systems = BusinessSystem.query.filter(BusinessSystem.id.in_(system_ids)).all()
    user.authorized_systems = systems
    
    db.session.commit()
    flash('用户更新成功', 'success')
    return redirect(url_for('user.list_users'))

@bp.route('/users/delete/<int:id>')
def delete_user(id):
    if id == current_user.id:
        flash('不能删除自己', 'danger')
        return redirect(url_for('user.list_users'))
        
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    flash('用户删除成功', 'success')
    return redirect(url_for('user.list_users'))
