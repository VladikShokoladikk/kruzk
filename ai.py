# pip install python-telegram-bot moviepy pillow numpy whisper pydub

import os
import numpy as np
from PIL import Image, ImageDraw
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from moviepy import VideoFileClip
import whisper
from pydub import AudioSegment

# === Настройки ===
BOT_TOKEN = "7874984007:AAGMTVucWgxluL3pzy10QJsDdnvWUb-LRZ0"
model = whisper.load_model("medium")

# --- Функция для создания круговой маски ---
def make_circle_mask(size):
    w, h = size
    mask_img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask_img)
    radius = min(w, h) // 2
    center = (w // 2, h // 2)
    draw.ellipse((center[0] - radius, center[1] - radius,
                  center[0] + radius, center[1] + radius),
                 fill=255)
    mask_array = np.array(mask_img).astype('float32') / 255.0
    return mask_array


# --- Команда /start ---
async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Привет, {update.effective_user.first_name}!')


# --- Управление состоянием: Видео-кружки ---
async def toggle_video_circle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = context.user_data.get("enable_video_circle", True)
    new_state = not current
    context.user_data["enable_video_circle"] = new_state
    status = "включено" if new_state else "выключено"
    await update.message.reply_text(f"Создание кружков из видео теперь {status}.")


# --- Управление состоянием: Распознавание голоса ---
async def toggle_voice_transcribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = context.user_data.get("enable_voice_transcribe", True)
    new_state = not current
    context.user_data["enable_voice_transcribe"] = new_state
    status = "включено" if new_state else "выключено"
    await update.message.reply_text(f"Транскрибация голосовых сообщений теперь {status}.")


# --- Обработка входящего видео ---
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, включена ли функция
    if not context.user_data.get("enable_video_circle", True):
        await update.message.reply_text("Создание кружков из видео временно отключено.")
        return

    if not update.message.video:
        await update.message.reply_text("Это не видео!")
        return
    print("Получено сообщение:", update.to_dict())  # Логируем всё сообщение
    if not update.message or not update.message.video:
        await update.message.reply_text("Видео не найдено.")

    await update.message.reply_text("Видео получено. Начинаю обработку...")

    video_file = await update.message.video.get_file()
    file_id = update.message.video.file_id
    original_path = os.path.join('downloads', f"{file_id}.mp4")
    cropped_path = os.path.join('downloads', f"{file_id}_cropped.mp4")

    os.makedirs('downloads', exist_ok=True)

    await video_file.download_to_drive(original_path)

    try:
        clip = VideoFileClip(original_path)

        # Обрезаем до квадрата по центру
        width, height = clip.size
        min_side = min(width, height)
        x_center = width / 2
        y_center = height / 2

        cropped_clip = clip.cropped(
            x1=x_center - min_side / 2,
            y1=y_center - min_side / 2,
            x2=x_center + min_side / 2,
            y2=y_center + min_side / 2
        )

        # Сохраняем видео
        cropped_clip.write_videofile(cropped_path, codec='libx264', audio_codec='aac')

        # Отправляем как video_note
        with open(cropped_path, 'rb') as f:
            await context.bot.send_video_note(
                chat_id=update.effective_chat.id,
                video_note=f
            )

        await update.message.reply_text("Видео успешно обработано и отправлено!")

    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке видео: {e}")

    finally:
        # Очистка
        for path in [original_path, cropped_path]:
            if os.path.exists(path):
                os.remove(path)


# === Обработка голосового сообщения ===
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, включена ли транскрибация
    if not context.user_data.get("enable_voice_transcribe", True):
        await update.message.reply_text("Транскрибация голосовых сообщений отключена.")
        return

    await update.message.reply_text("Аудио получено. Начинаю обработку...")
    file_id = update.message.voice.file_id
    new_file = await context.bot.get_file(file_id)
    file_path = f"{file_id}.ogg"
    await new_file.download_to_drive(file_path)

    text = recognize_speech(file_path)
    if text:
        await update.message.reply_text(f"Вы сказали: {text}")
    else:
        await update.message.reply_text("Не удалось распознать речь.")


# === Функция распознавания ===
def recognize_speech(file_path):
    wav_file = "output.wav"
    # Конвертируем OGG → WAV
    audio = AudioSegment.from_ogg(file_path)
    audio.export(wav_file, format="wav")

    # Распознавание
    result = model.transcribe(wav_file)
    return result["text"]


# --- Точка входа ---
async def post_init(application: ApplicationBuilder):
    await application.bot.set_my_commands([
        ('start', 'Начать работу с ботом'),
        ('toggle_video_circle', 'Включить/выключить создание кружков из видео'),
        ('toggle_voice_transcribe', 'Включить/выключить транскрибацию голосовых сообщений')
    ])

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # Регистрация команд
    application.add_handler(CommandHandler("start", hello))
    application.add_handler(CommandHandler("toggle_video_circle", toggle_video_circle))
    application.add_handler(CommandHandler("toggle_voice_transcribe", toggle_voice_transcribe))

    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("Бот запущен. Ожидание сообщений...")
    application.run_polling()