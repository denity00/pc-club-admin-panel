from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import datetime
from app import app, Computer, Booking, User, db
from datetime import datetime, timedelta

TOKEN = "qwe"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🖥️ Список компьютеров", callback_data='list_computers')],
        [InlineKeyboardButton("⏰ Мои бронирования", callback_data='my_bookings')],
        [InlineKeyboardButton("📅 Забронировать", callback_data='book_computer')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Добро пожаловать в систему бронирования компьютерного клуба!",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'list_computers':
        await list_computers(update, context)
    elif query.data == 'my_bookings':
        await my_bookings(update, context)
    elif query.data == 'book_computer':
        await choose_computer(update, context)
    elif query.data.startswith('computer_'):
        computer_id = int(query.data.split('_')[1])
        context.user_data['computer_id'] = computer_id
        await choose_date(update, context)
    elif query.data.startswith('date_'):
        date_str = query.data.split('_')[1]
        await choose_time(update, context, date_str)
    elif query.data.startswith('time_'):
        await handle_time_selection(update, context)

async def list_computers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with app.app_context():
        computers = Computer.query.filter_by(is_active=True).all()
    
    message = "🖥️ Доступные компьютеры:\n\n"
    for comp in computers:
        message += f"{comp.name} - {comp.specs}\n"
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message
    )

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    with app.app_context():
        # Используем joinedload для сразу подгружать связанные данные
        from sqlalchemy.orm import joinedload
        
        user = User.query.filter_by(telegram_id=update.effective_user.id).first()
        if not user:
            message = "У вас нет активных бронирований"
            if query:
                await query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return
            
        # Загружаем бронирования с компьютерами сразу
        bookings = db.session.query(Booking)\
            .options(joinedload(Booking.computer))\
            .filter_by(user_id=user.id)\
            .order_by(Booking.start_time)\
            .all()
    
        if not bookings:
            message = "У вас нет активных бронирований"
            if query:
                await query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return
        
        message = "📅 Ваши бронирования:\n\n"
        for booking in bookings:
            message += (
                f"🖥️ {booking.computer.name}\n"
                f"📅 {booking.start_time.strftime('%d.%m.%Y')}\n"
                f"⏰ {booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}\n"
                f"🔹 {booking.computer.specs}\n\n"
            )
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(
                text=message,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=message,
                reply_markup=reply_markup
            )

async def choose_computer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with app.app_context():
        computers = Computer.query.filter_by(is_active=True).all()
    
    keyboard = []
    for comp in computers:
        keyboard.append([InlineKeyboardButton(comp.name, callback_data=f'computer_{comp.id}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите компьютер:",
        reply_markup=reply_markup
    )

async def choose_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().date()
    keyboard = []
    
    for i in range(7):
        date = today + timedelta(days=i)
        keyboard.append(
            [InlineKeyboardButton(date.strftime('%d.%m.%Y'), callback_data=f'date_{date.strftime("%Y-%m-%d")}')]
        )
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите дату:",
        reply_markup=reply_markup
    )


async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str):
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    now = datetime.now()
    
    if selected_date == now.date():
        start_hour = now.hour + 1
    else:
        start_hour = 10  # Клуб открывается в 10:00
    
    keyboard = []
    for hour in range(start_hour, 22):  # Клуб работает до 22:00
        for minute in ['00', '30']:  # Добавляем выбор каждые 30 минут
            if hour == 21 and minute == '30':  # Последний доступный слот
                continue
            time_str = f"{hour:02d}:{minute}"
            keyboard.append(
                [InlineKeyboardButton(time_str, callback_data=f'time_{date_str}_{time_str}')]
            )
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите время начала:",
        reply_markup=reply_markup
    )

async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, date_str, time_str = query.data.split('_')
        start_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        end_time = start_time + timedelta(hours=1)
        
        with app.app_context():
            computer_id = context.user_data['computer_id']
            
            # Проверяем доступность
            if not is_computer_available(computer_id, start_time, end_time):
                await query.edit_message_text("Это время уже занято. Пожалуйста, выберите другое время.")
                return
            
            # Создаем/находим пользователя
            user = User.query.filter_by(telegram_id=query.from_user.id).first()
            if not user:
                user = User(
                    username=query.from_user.full_name,
                    telegram_id=query.from_user.id,
                    phone="from_telegram"
                )
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
            
            computer = Computer.query.get(computer_id)
            await query.edit_message_text(
                f"✅ Бронирование подтверждено!\n\n"
                f"🖥️ Компьютер: {computer.name}\n"
                f"📅 Дата: {start_time.strftime('%d.%m.%Y')}\n"
                f"⏰ Время: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}\n\n"
                f"Чтобы посмотреть все свои бронирования, нажмите /mybookings"
            )
    except Exception as e:
        print(f"Error: {e}")
        await query.edit_message_text("Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте еще раз.")

def is_computer_available(computer_id, start_time, end_time):
    overlapping = Booking.query.filter(
        Booking.computer_id == computer_id,
        Booking.start_time < end_time,
        Booking.end_time > start_time
    ).count()
    return overlapping == 0

def setup_handlers(application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CommandHandler("mybookings", my_bookings))

def run_bot():
    application = Application.builder().token(TOKEN).build()
    setup_handlers(application)
    application.run_polling()

if __name__ == "__main__":
    run_bot()