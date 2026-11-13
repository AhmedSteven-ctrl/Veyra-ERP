#!/bin/sh
# بيشتغل كل مرة الحاوية تقوم: يتأكد إن ملفات migrations موجودة ومطابقة للموديلات، يطبّقها، وبعدين يشغّل السيرفر.
set -e

if [ ! -d accounts/migrations ]; then
  echo "خطأ: مفيش ملفات migrations في المشروع." >&2
  echo "شغّل محلياً: python manage.py makemigrations accounts core inventory accounting sales purchasing" >&2
  echo "وبعدها ابني الصورة تاني (ملفات migrations لازم تكون جزء من المشروع)." >&2
  exit 1
fi

# لو الموديلات اتغيّرت من غير migration جديد، نوقف بدل ما نشغّل نظام قاعدته مش مطابقة للكود
python manage.py makemigrations --check --dry-run >/dev/null || {
  echo "خطأ: الموديلات فيها تغييرات من غير migration. شغّل makemigrations محلياً وضيف الملفات." >&2
  exit 1
}

python manage.py migrate --noinput
exec "$@"
