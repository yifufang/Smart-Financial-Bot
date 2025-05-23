from django.shortcuts import render
import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST
from .models import ChatMessage
from django.views.decorators.csrf import csrf_exempt
import requests
from django.db.models import Count, Sum
from .models import Finance
from django.core.paginator import Paginator
import logging
from django.conf import settings

# Create your views here.

def chat_view(request):
    return render(request, 'finance/chat.html', {'FLASK_URL':settings.FLASK_URL})

@csrf_exempt
@require_http_methods(["POST"])
def save_chat_message(request):
    try:
        data = json.loads(request.body)
        message = data.get("message", "")
        sender = data.get("sender", "")
        if message and sender:
            ChatMessage.objects.create(message=message, sender=sender)
            return JsonResponse({"status": "success"})
        return JsonResponse({"status": "error", "error": "Invalid data"}, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)

@require_http_methods(["GET"])
def get_chat_history(request):
    messages = ChatMessage.objects.all().order_by("created_at")
    data = [{"message": m.message, "sender": m.sender} for m in messages]
    return JsonResponse(data, safe=False)

@csrf_exempt
@require_POST
def clear_chat_history(request):
    ChatMessage.objects.all().delete()
    return JsonResponse({'status': 'success'})

@csrf_exempt
@require_http_methods(["POST"])
def get_rasa_response(request):
    logger = logging.getLogger(__name__)
    try:
        data = json.loads(request.body)
        message = data.get("message", "")
        sender = data.get("sender", "default")
        if not message:
            return JsonResponse({"status": "error", "error": "No message provided."}, status=400)
        payload = {"sender": sender, "message": message}
        rasa_endpoint = "http://localhost:5005/webhooks/rest/webhook"  # update if needed
        logger.info("Sending payload to Rasa: %s", payload)
        try:
            rasa_resp = requests.post(rasa_endpoint, json=payload, timeout=60)
        except requests.exceptions.ReadTimeout:
            # Handle timeout error gracefully
            return HttpResponse("Rasa server timeout. Please try again later.", status=504)
        logger.info("Rasa response status code: %s", rasa_resp.status_code)
        if rasa_resp.status_code == 200:
            responses = rasa_resp.json()
            logger.info("Rasa responses: %s", responses)
            return JsonResponse({"status": "success", "responses": responses})
        else:
            error_msg = f"Rasa error {rasa_resp.status_code}: {rasa_resp.text}"
            logger.error(error_msg)
            return JsonResponse({"status": "error", "error": error_msg}, status=500)
    except Exception as e:
        logger.exception("Exception in get_rasa_response")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)
    

@require_http_methods(["GET"])
def get_category_data(request):
    # get category data
    data = list(Finance.objects.values('category').annotate(count=Count('category')))
    return JsonResponse(data, safe=False)

@require_http_methods(["GET"])
def get_category_amount_data(request):
    trans_type = request.GET.get("type", "Expense")
    if trans_type not in ["Expense", "Income"]:
        trans_type = "Expense"
    data = list(Finance.objects.filter(type=trans_type)
                .values('category')
                .annotate(total=Sum('amount'))
                .order_by('-total'))
    return JsonResponse(data, safe=False)

    

def transactions_api(request):
    filter_val = request.GET.get('filter', '')
    order_by = request.GET.get('order_by', 'date')
    direction = request.GET.get('direction', 'desc')
    page_number = request.GET.get('page', 1)

    valid_fields = {
        'date': 'date',
        'category': 'category',
        'amount': 'amount',
        'type': 'type',
        'description': 'transaction_Description'
    }
    sort_field = valid_fields.get(order_by, 'date')
    sort_prefix = '' if direction == 'asc' else '-'
    
    qs = Finance.objects.all()
    if filter_val:
        qs = qs.filter(category__icontains=filter_val)
    qs = qs.order_by(f"{sort_prefix}{sort_field}")

    paginator = Paginator(qs, 5)
    page_obj = paginator.get_page(page_number)
    transactions = []
    for i, trans in enumerate(page_obj.object_list, start=1):
        transactions.append({
            'counter': i,
            'date': trans.date.strftime('%Y-%m-%d %H:%M:%S'),
            'category': trans.category,
            'amount': trans.amount,
            'type': trans.type,
            'description': trans.transaction_Description
        })
    data = {
        'transactions': transactions,
        'page': page_obj.number,
        'total_pages': paginator.num_pages,
        'has_previous': page_obj.has_previous(),
        'has_next': page_obj.has_next(),
        'previous_page_number': page_obj.previous_page_number() if page_obj.has_previous() else None,
        'next_page_number': page_obj.next_page_number() if page_obj.has_next() else None,
    }
    return JsonResponse(data)

@csrf_exempt
@require_http_methods(["POST"])
def accept_image(request):
    try:
        if 'image' not in request.FILES:
            return JsonResponse({"status": "error", "error": "No image provided."}, status=400)
        # For demonstration, simply return a text acknowledgement.
        
        return JsonResponse({"status": "success", "text": "Image received"})
    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)
    
@csrf_exempt
@require_http_methods(["POST"])
def process_text_from_flask(request):
    try:
        data = json.loads(request.body)
        text = data.get("text", "")
        if not text:
            return JsonResponse({"status": "error", "error": "No text provided."}, status=400)
        
        # Send the extracted text to Rasa for processing.
        rasa_endpoint = "http://localhost:5005/webhooks/rest/webhook"
        payload = {
            "sender": "user",  # identifier for this sender
            "message": text
        }
        
        rasa_resp = requests.post(rasa_endpoint, json=payload, timeout=60)
        if rasa_resp.status_code != 200:
            error_msg = f"Rasa error {rasa_resp.status_code}: {rasa_resp.text}"
            return JsonResponse({"status": "error", "error": error_msg}, status=500)
        print(rasa_resp)
        responses = rasa_resp.json()  # Expecting a list of response messages from Rasa.
        return JsonResponse({"status": "success", "responses": responses})
    except Exception as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=500)
