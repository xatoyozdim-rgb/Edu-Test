import re
from docx import Document
from django.db import transaction
from .models import Question, Option, TestAttempt

def parse_docx_to_test(docx_file, test_obj):
    doc = Document(docx_file)
    curr_q = None
    order = test_obj.questions.count() + 1
    q_re = re.compile(r'^(\d+)[\.\)]\s*(.+)')
    o_re = re.compile(r'^([\*+#]?)([A-Da-d])[\.\)]\s*(.+)')
    ans_re = re.compile(r'^Javob[:\s]*(.+)', re.IGNORECASE)

    temp_options = []

    def save_current_question():
        nonlocal curr_q, temp_options, order
        if curr_q:
            if temp_options:
                correct_count = sum(1 for o in temp_options if o['is_correct'])
                if correct_count > 1:
                    curr_q.question_type = 'multiple'
                else:
                    curr_q.question_type = 'single'
                curr_q.save()
                for opt in temp_options:
                    Option.objects.create(question=curr_q, text=opt['text'], is_correct=opt['is_correct'])
            temp_options = []

    with transaction.atomic():
        for p in doc.paragraphs:
            line = p.text.strip()
            if not line: continue
            
            qm = q_re.match(line)
            om = o_re.match(line)
            ansm = ans_re.match(line)

            if qm and not om:
                save_current_question()
                curr_q = Question.objects.create(
                    test=test_obj, 
                    text=str(qm.group(2)).strip().capitalize(), 
                    order=order, 
                    question_type='single'
                )
                order += 1
            elif om and curr_q:
                is_corr = bool(om.group(1))
                opt_text = str(om.group(3)).strip().capitalize()
                temp_options.append({'text': opt_text, 'is_correct': is_corr})
            elif ansm and curr_q:
                ans_text = str(ansm.group(1)).strip().capitalize()
                curr_q.question_type = 'open'
                curr_q.correct_text_answers = ans_text
                curr_q.save()
        save_current_question()

def recalculate_test_scores(test_obj):
    total_q = test_obj.questions.count()
    for att in TestAttempt.objects.filter(test=test_obj).prefetch_related('answers__selected_options', 'answers__selected_option', 'answers__question'):
        score = 0.0
        correct = 0
        for ans in att.answers.all():
            q = ans.question
            if q.question_type == 'single':
                if ans.selected_option and ans.selected_option.is_correct:
                    score += q.points
                    correct += 1
            elif q.question_type == 'multiple':
                correct_opts = set(q.options.filter(is_correct=True).values_list('id', flat=True))
                selected_opts = set(ans.selected_options.values_list('id', flat=True))
                if correct_opts and correct_opts == selected_opts:
                    score += q.points
                    correct += 1
            elif q.question_type == 'open':
                if ans.text_answer and q.correct_text_answers:
                    student_val = str(ans.text_answer).strip().capitalize()
                    accepted = [str(a).strip().capitalize() for a in q.correct_text_answers.split(',')]
                    if student_val in accepted:
                        score += q.points
                        correct += 1
        att.score = score
        att.correct_count = correct
        att.total_questions = total_q
        att.save()
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

def upload_to_user_drive(access_token, file_name, file_bytes, mime_type="application/json"):
    try:
        creds = Credentials(token=access_token)
        service = build('drive', 'v3', credentials=creds)

        file_metadata = {'name': file_name}
        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes), 
            mimetype=mime_type, 
            resumable=True
        )

        # 1. Faylni yuklaymiz
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        file_id = file.get('id')

        # 2. O'quvchilar ko'rishi uchun fayl ruxsatini "Hammaga ochiq" qilamiz
        permission = {
            'type': 'anyone',
            'role': 'reader',
        }
        service.permissions().create(
            fileId=file_id,
            body=permission
        ).execute()

        return {
            'success': True,
            'file_id': file_id,
            'link': file.get('webViewLink')
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
