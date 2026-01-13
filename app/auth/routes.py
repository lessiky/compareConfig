from flask import Blueprint, render_template, redirect, url_for, flash, request, session, Response
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app import db
import random
import string
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

bp = Blueprint('auth', __name__)

def generate_captcha():
    # 生成随机字符串
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    
    # 创建图片
    width, height = 120, 40
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # 绘制干扰点
    for _ in range(100):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(random.randint(0, 200), random.randint(0, 200), random.randint(0, 200)))
        
    # 绘制验证码
    # 简单起见，不加载自定义字体，直接画上去或者用默认字体（Pillow默认字体可能很小）
    # 这里为了兼容性，尝试使用简单的绘制方式，或者加载默认字体
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except:
        font = ImageFont.load_default()
        
    for i, char in enumerate(code):
        color = (random.randint(0, 150), random.randint(0, 150), random.randint(0, 150))
        draw.text((20 + i * 20, 5), char, font=font, fill=color)
        
    return code, image

@bp.route('/captcha')
def captcha():
    code, image = generate_captcha()
    session['captcha'] = code.lower()
    
    img_io = BytesIO()
    image.save(img_io, 'PNG')
    img_io.seek(0)
    return Response(img_io.getvalue(), mimetype='image/png')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        captcha_code = request.form.get('captcha')
        
        if not captcha_code or captcha_code.lower() != session.get('captcha', ''):
            flash('验证码错误', 'danger')
            return render_template('auth/login.html')
            
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash('用户名或密码错误', 'danger')
            return render_template('auth/login.html')
            
        if not user.is_active:
            flash('账号已被禁用', 'warning')
            return render_template('auth/login.html')
            
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('main.index')
        return redirect(next_page)
        
    return render_template('auth/login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
