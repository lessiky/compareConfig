from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.models import BusinessSystem, User, Server
from app import db

bp = Blueprint('system', __name__)

@bp.before_request
@login_required
def require_login():
    pass

@bp.route('/systems')
def list_systems():
    if not current_user.is_admin:
        abort(403)
    systems = BusinessSystem.query.all()
    return render_template('system/list.html', systems=systems)

@bp.route('/systems/add', methods=['POST'])
def add_system():
    if not current_user.is_admin:
        abort(403)
    name = request.form.get('name')
    description = request.form.get('description')
    
    if BusinessSystem.query.filter_by(name=name).first():
        flash('业务系统名称已存在', 'danger')
        return redirect(url_for('system.list_systems'))
        
    system = BusinessSystem(name=name, description=description)
    db.session.add(system)
    db.session.commit()
    flash('业务系统添加成功', 'success')
    return redirect(url_for('system.list_systems'))

@bp.route('/systems/edit/<int:id>', methods=['POST'])
def edit_system(id):
    if not current_user.is_admin:
        abort(403)
    system = BusinessSystem.query.get_or_404(id)
    system.name = request.form.get('name')
    system.description = request.form.get('description')
    db.session.commit()
    flash('业务系统更新成功', 'success')
    return redirect(url_for('system.list_systems'))

@bp.route('/systems/delete/<int:id>')
def delete_system(id):
    if not current_user.is_admin:
        abort(403)
    system = BusinessSystem.query.get_or_404(id)
    if system.servers.count() > 0:
        flash('无法删除：该业务系统下有关联的服务器', 'danger')
        return redirect(url_for('system.list_systems'))
        
    db.session.delete(system)
    db.session.commit()
    flash('业务系统删除成功', 'success')
    return redirect(url_for('system.list_systems'))
