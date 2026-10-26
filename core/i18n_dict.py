"""ترجمة واجهة Veyra للإنجليزي. المفتاح = النص العربي كما هو في الكود.
أي نص مش موجود هنا بيفضل عربي (ومن غير ما الشاشة تقع)."""

EN = {
    # عام
    "الرئيسية": "Home", "التطبيقات": "Apps", "كل التطبيقات": "All apps", "بحث شامل": "Global search",
    "بحث شامل (قريباً)": "Global search (soon)", "بحث...": "Search...", "بحث": "Search",
    "دخول": "Sign in", "خروج": "Sign out", "تسجيل الخروج": "Sign out", "تغيير كلمة المرور": "Change password",
    "تفضيلاتي": "Preferences", "المساعدة": "Help", "حسابي": "My account",
    "مدير النظام": "System admin", "مدير الشركة": "Company manager", "مستخدم": "User",
    "جديد": "New", "إجراءات": "Actions", "طباعة": "Print", "تصدير المحدد CSV": "Export selected (CSV)",
    "تحديد الكل": "Select all", "إلغاء التحديد": "Clear selection", "محدد": "selected",
    "حفظ": "Save", "إلغاء": "Cancel", "رجوع": "Back", "تعديل": "Edit", "حذف": "Delete", "أرشفة": "Archive",
    "الإجمالي": "Total", "لا توجد سجلات": "No records", "مفيش تفاصيل": "No details",
    "قريباً": "Soon", "افتح": "Open", "فرعي": "sub", "مرحباً": "Welcome",
    "اختار المديول اللي عايز تشتغل عليه · اسحب الكروت لترتيبها": "Choose a module · drag cards to reorder",
    "مفيش مديولات مفعّلة ليك دلوقتي.": "No modules are enabled for you yet.",
    "المديولات الفرعية": "Sub-modules", "لإضافة صنف جديد احفظ الأمر، وبعدها ارجع عدّل وضيف الصنف التاني.":
        "To add another item, save the order first, then edit it.",
    "الصنف": "Item", "الكمية": "Quantity", "السعر": "Price", "حذف الصنف": "Remove",
    "الكود": "Code", "الاسم": "Name", "الوحدة": "Unit", "سعر البيع": "Sale price",
    "حد إعادة الطلب": "Reorder level", "الرصيد": "Balance", "الرصيد الحالي": "Current balance",
    "الحالة": "Status", "الرقم": "Number", "العميل": "Customer", "المورد": "Supplier", "التكلفة": "Cost",
    "الهاتف": "Phone", "المدينة": "City", "النوع": "Type", "المعلومات": "Information",
    "السجل والتعديلات": "History & changes", "التفاصيل": "Details", "الأصناف": "Items",
    "اسم المستخدم": "Username", "كلمة المرور": "Password", "كلمة المرور الحالية": "Current password",
    "كلمة المرور الجديدة": "New password", "تأكيد كلمة المرور الجديدة": "Confirm new password",
    "حفظ كلمة المرور الجديدة": "Save new password",
    "اسم المستخدم أو كلمة المرور غير صحيحة.": "Invalid username or password.",
    "كلمة المرور الحالية مؤقتة. لازم تغيّرها قبل ما تكمل.": "Your current password is temporary. Please change it to continue.",
    "تسجيل الدخول": "Sign in", "ادخل بحسابك للمتابعة": "Sign in to continue",
    "الشركة": "Company", "الباقة": "Plan",
    # الحالات
    "مسودة": "Draft", "مؤكد": "Confirmed", "بانتظار التسليم": "Awaiting delivery", "تم التسليم": "Delivered",
    "بانتظار الاستلام": "Awaiting receipt", "مستلم": "Received", "متوفر": "In stock",
    "تحت حد الطلب": "Below reorder level", "عميل": "Customer", "مورد": "Supplier", "عميل ومورد": "Customer & supplier",
    "نشط": "Active", "أرشيف": "Archived", "منتهي": "Ended", "مكتمل": "Completed", "قيد التنفيذ": "In progress",
    # القوائم والأزرار
    "المنتجات والأرصدة": "Products & stock", "أوامر البيع": "Sales orders", "أوامر الشراء": "Purchase orders",
    "جهات الاتصال": "Contacts", "المنتجات": "Products", "الكل": "All",
    "أمر بيع جديد": "New sales order", "أمر شراء جديد": "New purchase order", "صنف جديد": "New item",
    "جهة اتصال جديدة": "New contact", "تسليم وخصم من المخزن": "Deliver & issue stock",
    "استلام وإدخال للمخزن": "Receive into stock", "⋯ إجراءات": "⋯ Actions",
    "سعر البيع": "Sale price",
    # المديولات
    "المخزون": "Inventory", "المبيعات": "Sales", "الشراء": "Purchasing", "المحاسبة": "Accounting",
    "الموظفون": "Employees", "التصنيع": "Manufacturing", "الجودة": "Quality", "الصيانة": "Maintenance",
    "المشروع": "Project", "التخطيط": "Planning", "التقويم": "Calendar", "المناقشة": "Discuss",
    "المعرفة": "Knowledge", "المستندات": "Documents", "توقيع": "Sign", "الاستطلاعات": "Surveys",
    "التعلم الإلكتروني": "E-learning", "الموقع الإلكتروني": "Website", "لوحات البيانات": "Dashboards",
    "المواعيد": "Appointments", "باركود": "Barcode", "شاشة التصنيع": "Shop floor", "المهام": "Tasks",
    "الذكاء الاصطناعي": "AI", "رأس المال": "Capital", "تذاكر الدعم": "Helpdesk", "الأسطول": "Fleet",
    "التأجير": "Rental", "الاشتراكات": "Subscriptions", "المصروفات": "Expenses", "التوظيف": "Recruitment",
    "الحضور": "Attendance", "الإجازات": "Time off", "تقييم الأداء": "Appraisals",
    "التسويق بالبريد": "Email marketing", "الفعاليات": "Events", "المتجر الإلكتروني": "E-commerce",
    "الدردشة المباشرة": "Live chat", "الإعدادات": "Settings", "إدارة علاقات العملاء": "CRM",
    "متتبع الروابط": "Link tracker", "أتمتة التسويق": "Marketing automation",
    "المناقشة (الجروبات والشات)": "Discuss (groups & chat)", "تسجيل الوقت": "Timesheets",
    "الأصول الثابتة": "Fixed assets", "WhatsApp": "WhatsApp", "الفواتير": "Invoices",
    # الشكل
    "الوضع الداكن": "Dark mode", "الوضع الفاتح": "Light mode", "اللغة": "Language",
}


# الباركود وتأكيد الأوامر وتكلفة الصنف
EN.update({
    "الباركود": "Barcode", "باركود": "Barcode", "تكلفة الوحدة": "Unit cost",
    "تأكيد الأمر": "Confirm order", "تسليم وخصم من المخزن": "Deliver & issue stock",
    "استلام وإدخال للمخزن": "Receive into stock", "تعديل": "Edit",
})


def translate(text, lang):
    if lang == "en":
        return EN.get(text, text)
    return text
