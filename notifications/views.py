from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Notification


@login_required
def inbox(request):
    return render(request, "notifications/inbox.html", {"notifications": Notification.objects.filter(user=request.user)})
