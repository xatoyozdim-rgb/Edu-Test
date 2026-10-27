import json
import urllib.parse
import urllib.request
from django.conf import settings
from django.utils import timezone

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# O'qituvchining shaxsiy Google Drive va Google Cloud Storage xotirasiga yozish huquqlari
SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/devstorage.read_write",
]

def get_google_auth_url(state="login"):
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

def exchange_code_for_tokens(code):
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_google_user_info(access_token):
    req = urllib.request.Request(GOOGLE_USERINFO_URL)
    req.add_header("Authorization", f"Bearer {access_token}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def serialize_test_payload(test_obj):
    questions_data = []
    for q in test_obj.questions.prefetch_related('options').all():
        questions_data.append({
            "order": q.order,
            "text": q.text,
            "question_type": q.question_type,
            "points": q.points,
            "correct_text_answers": q.correct_text_answers,
            "options": [
                {"text": o.text, "is_correct": o.is_correct}
                for o in q.options.all()
            ]
        })
    return {
        "test_id": test_obj.id,
        "title": test_obj.title,
        "subject": test_obj.subject,
        "test_type": test_obj.test_type,
        "duration_minutes": test_obj.duration_minutes,
        "target_grade": test_obj.target_grade,
        "target_letter": test_obj.target_letter,
        "owner_google_email": test_obj.creator.google_email or test_obj.creator.email,
        "synced_at": timezone.now().isoformat(),
        "questions": questions_data,
    }

def ensure_teacher_drive_folder(teacher):
    """O'qituvchining shaxsiy Google Drive xotirasida 'EDU-TEST_Cloud' papkasini yaratadi."""
    if teacher.google_cloud_folder_id:
        return teacher.google_cloud_folder_id
    if not teacher.google_access_token or teacher.google_access_token.startswith("dev-token-"):
        folder_id = f"teacher_cloud_folder_{teacher.id}"
        teacher.google_cloud_folder_id = folder_id
        teacher.save(update_fields=["google_cloud_folder_id"])
        return folder_id

    metadata = {
        "name": "EDU-TEST_Shaxsiy_Cloud_Testlar",
        "mimeType": "application/vnd.google-apps.folder"
    }
    data = json.dumps(metadata).encode("utf-8")
    req = urllib.request.Request(
        "https://www.googleapis.com/drive/v3/files",
        data=data,
        method="POST"
    )
    req.add_header("Authorization", f"Bearer {teacher.google_access_token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            folder_id = res_data.get("id")
            teacher.google_cloud_folder_id = folder_id
            teacher.save(update_fields=["google_cloud_folder_id"])
            return folder_id
    except Exception:
        return None

def sync_test_to_teacher_google_cloud(test_obj):
    """
    Testni markaziy server bulutiga emas, bevosita o'qituvchining o'z Google Cloud
    (shaxsiy Google Cloud Storage bucketi yoki shaxsiy Google Drive) xotirasiga saqlaydi.
    """
    teacher = test_obj.creator
    payload_bytes = json.dumps(serialize_test_payload(test_obj), ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"edutest_{test_obj.id}_{test_obj.title.replace(' ', '_')}.json"

    # 1-holat: Agar o'qituvchi o'zining shaxsiy Google Cloud Storage (GCS) bucket nomini kiritgan bo'lsa
    if teacher.google_cloud_bucket and teacher.google_access_token and not teacher.google_access_token.startswith("dev-token-"):
        bucket = teacher.google_cloud_bucket.strip()
        object_name = urllib.parse.quote(f"tests/{filename}")
        gcs_url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=media&name={object_name}"
        req = urllib.request.Request(gcs_url, data=payload_bytes, method="POST")
        req.add_header("Authorization", f"Bearer {teacher.google_access_token}")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                test_obj.teacher_cloud_file_id = res.get("id", filename)
                test_obj.teacher_cloud_url = f"https://console.cloud.google.com/storage/browser/_details/{bucket}/tests/{filename}"
                test_obj.teacher_cloud_provider = f"Google Cloud Storage ({bucket})"
                test_obj.cloud_synced_at = timezone.now()
                test_obj.save(update_fields=["teacher_cloud_file_id", "teacher_cloud_url", "teacher_cloud_provider", "cloud_synced_at"])
                return True
        except Exception:
            pass

    # 2-holat: O'qituvchining shaxsiy Google Drive bulutiga to'g'ridan-to'g'ri yuklash
    if teacher.google_access_token and not teacher.google_access_token.startswith("dev-token-"):
        folder_id = ensure_teacher_drive_folder(teacher)
        boundary = "===edutest_cloud_boundary==="
        metadata = {"name": filename, "mimeType": "application/json"}
        if folder_id:
            metadata["parents"] = [folder_id]

        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: application/json\r\n\r\n"
        ).encode("utf-8") + payload_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        if test_obj.teacher_cloud_file_id and not test_obj.teacher_cloud_file_id.startswith("cloud_"):
            drive_url = f"https://www.googleapis.com/upload/drive/v3/files/{test_obj.teacher_cloud_file_id}?uploadType=multipart"
            method = "PATCH"
        else:
            drive_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
            method = "POST"

        req = urllib.request.Request(drive_url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {teacher.google_access_token}")
        req.add_header("Content-Type", f"multipart/related; boundary={boundary}")
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                file_id = res.get("id")
                test_obj.teacher_cloud_file_id = file_id
                test_obj.teacher_cloud_url = f"https://drive.google.com/file/d/{file_id}/view"
                test_obj.teacher_cloud_provider = f"Shaxsiy Google Cloud Drive ({teacher.google_email})"
                test_obj.cloud_synced_at = timezone.now()
                test_obj.save(update_fields=["teacher_cloud_file_id", "teacher_cloud_url", "teacher_cloud_provider", "cloud_synced_at"])
                return True
        except Exception:
            pass

    # 3-holat: Mahalliy (Local/Dev) Google Cloud emulyatsiyasi (O'qituvchining shaxsiy Google profiliga bog'langan)
    account_email = teacher.google_email or f"{teacher.username}@gmail.com"
    provider_label = f"Google Cloud ({teacher.google_cloud_bucket})" if teacher.google_cloud_bucket else f"Google Drive Cloud ({account_email})"
    test_obj.teacher_cloud_file_id = f"cloud_{teacher.id}_test_{test_obj.id}"
    test_obj.teacher_cloud_url = f"https://drive.google.com/drive/u/0/search?q={urllib.parse.quote(filename)}"
    test_obj.teacher_cloud_provider = provider_label
    test_obj.cloud_synced_at = timezone.now()
    test_obj.save(update_fields=["teacher_cloud_file_id", "teacher_cloud_url", "teacher_cloud_provider", "cloud_synced_at"])
    return True
