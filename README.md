# EduTest — Onlayn Test Platformasi

Django + Tailwind CSS asosidagi onlayn test platformasi.

## Xususiyatlar

- 👨‍🏫 O'qituvchilar test yaratish (qo'lda / matndan / fayldan)
- 👨‍🎓 O'quvchilar test topshirish (fullscreen + qoidabuzarlik)
- 📊 Real-time monitoring, reytinglar, Excel eksport
- ⚠️ Apellyatsiya va shikoyat tizimi
- 👑 Admin panel (o'qituvchilarni tasdiqlash, natijalarni tozalash)
- 🔒 Exam uchun fullscreen + multi-monitor himoyasi

## O'rnatish

```bash
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver