"""Lỗi API có thông báo cho UI, không trả traceback hoặc SQL cho người dùng."""
import logging
from functools import wraps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, IntegrityError
from django.http import Http404, JsonResponse

logger = logging.getLogger(__name__)


def api_errors(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except PermissionDenied as exc:
            return JsonResponse({'error': str(exc) or 'Không có quyền truy cập.'}, status=403)
        except Http404:
            return JsonResponse({'error': 'Không tìm thấy dữ liệu.'}, status=404)
        except ValidationError as exc:
            return JsonResponse({'error': exc.messages}, status=400)
        except IntegrityError:
            return JsonResponse({'error': 'Dữ liệu trùng hoặc đã thay đổi. Vui lòng tải lại.'}, status=409)
        except DatabaseError:
            logger.exception('Không truy cập được dữ liệu III–IV')
            return JsonResponse({'error': 'Không truy cập được dữ liệu, vui lòng thử lại.'}, status=503)
    return wrapped
