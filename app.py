from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///computer_club.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Модели базы данных
class Computer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    specs = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    bookings = db.relationship('Booking', backref='computer', lazy=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    bookings = db.relationship('Booking', backref='user', lazy=True)
    telegram_id = db.Column(db.String(50), unique=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    computer_id = db.Column(db.Integer, db.ForeignKey('computer.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()
    
    if Computer.query.count() == 0:
        computers = [
            Computer(name="PC-1", specs="Intel i7, 16GB RAM, RTX 3060"),
            Computer(name="PC-2", specs="Intel i5, 8GB RAM, GTX 1660"),
            Computer(name="PC-3", specs="Intel i9, 32GB RAM, RTX 3080"),
            Computer(name="PC-4", specs="AMD Ryzen 7, 16GB RAM, RX 6700"),
            Computer(name="VIP-1", specs="Intel i9, 64GB RAM, RTX 4090")
        ]
        db.session.bulk_save_objects(computers)
        db.session.commit()
    
    if User.query.filter_by(is_admin=True).count() == 0:
        admin = User(username="admin", phone="+1234567890", is_admin=True)
        db.session.add(admin)
        db.session.commit()


def is_computer_available(computer_id, start_time, end_time):
    overlapping_bookings = Booking.query.filter(
        Booking.computer_id == computer_id,
        Booking.start_time < end_time,
        Booking.end_time > start_time
    ).count()
    return overlapping_bookings == 0

def get_available_computers(start_time, end_time):
    all_computers = Computer.query.filter_by(is_active=True).all()
    available_computers = []
    for computer in all_computers:
        if is_computer_available(computer.id, start_time, end_time):
            available_computers.append(computer)
    return available_computers


@app.route('/')
def index():
    computers = Computer.query.filter_by(is_active=True).all()
    return render_template('index.html', computers=computers)

@app.route('/book', methods=['GET', 'POST'])
def book_computer():
    if request.method == 'POST':
        username = request.form.get('username')
        phone = request.form.get('phone')
        computer_id = int(request.form.get('computer_id'))
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        
        try:
            start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
            end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Неверный формат даты и времени', 'error')
            return redirect(url_for('book_computer'))
        
        if start_time >= end_time:
            flash('Время окончания должно быть позже времени начала', 'error')
            return redirect(url_for('book_computer'))
        
        if start_time < datetime.now():
            flash('Нельзя бронировать компьютер в прошлом', 'error')
            return redirect(url_for('book_computer'))
        
        # Проверяем, доступен ли компьютер
        if not is_computer_available(computer_id, start_time, end_time):
            flash('Этот компьютер уже забронирован на выбранное время', 'error')
            return redirect(url_for('book_computer'))
        
        # Находим или создаем пользователя
        user = User.query.filter_by(phone=phone).first()
        if not user:
            user = User(username=username, phone=phone)
            db.session.add(user)
            db.session.commit()
        
        # Создаем бронирование
        booking = Booking(
            user_id=user.id,
            computer_id=computer_id,
            start_time=start_time,
            end_time=end_time
        )
        db.session.add(booking)
        db.session.commit()
        
        flash('Компьютер успешно забронирован!', 'success')
        return redirect(url_for('index'))
    
    
    computers = Computer.query.filter_by(is_active=True).all()
    default_start = datetime.now() + timedelta(hours=1)
    default_end = default_start + timedelta(hours=1)
    return render_template('book.html', 
                         computers=computers,
                         default_start=default_start.strftime('%Y-%m-%dT%H:%M'),
                         default_end=default_end.strftime('%Y-%m-%dT%H:%M'))

@app.route('/check_availability', methods=['POST'])
def check_availability():
    start_time_str = request.form.get('start_time')
    end_time_str = request.form.get('end_time')
    
    try:
        start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        return {'error': 'Неверный формат даты и времени'}, 400
    
    if start_time >= end_time:
        return {'error': 'Время окончания должно быть позже времени начала'}, 400
    
    if start_time < datetime.now():
        return {'error': 'Нельзя бронировать компьютер в прошлом'}, 400
    
    available_computers = get_available_computers(start_time, end_time)
    computers_data = [{'id': c.id, 'name': c.name, 'specs': c.specs} for c in available_computers]
    
    return {'available_computers': computers_data}

@app.route('/admin')
def admin_panel():
    
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    
    bookings = Booking.query.order_by(Booking.start_time.desc()).all()
    computers = Computer.query.all()
    return render_template('admin.html', bookings=bookings, computers=computers)

@app.route('/admin/add_computer', methods=['POST'])
def add_computer():
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    
    name = request.form.get('name')
    specs = request.form.get('specs')
    
    if not name:
        flash('Название компьютера обязательно', 'error')
        return redirect(url_for('admin_panel'))
    
    computer = Computer(name=name, specs=specs)
    db.session.add(computer)
    db.session.commit()
    
    flash('Компьютер успешно добавлен', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/toggle_computer/<int:computer_id>')
def toggle_computer(computer_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    
    computer = Computer.query.get_or_404(computer_id)
    computer.is_active = not computer.is_active
    db.session.commit()
    
    flash(f'Компьютер {"активирован" if computer.is_active else "деактивирован"}', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_booking/<int:booking_id>')
def delete_booking(booking_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))
    
    booking = Booking.query.get_or_404(booking_id)
    db.session.delete(booking)
    db.session.commit()
    
    flash('Бронирование удалено', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        user = User.query.filter_by(username=username, is_admin=True).first()
        
        if user:
            session['is_admin'] = True
            flash('Вы успешно вошли как администратор', 'success')
            return redirect(url_for('admin_panel'))
        else:
            flash('Неверные учетные данные', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)