from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import AttendeeProfileForm
from .models import AttendeeProfile


@login_required
def profile(request):
    instance, _ = AttendeeProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = AttendeeProfileForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            return redirect("attendee-profile")
    else:
        form = AttendeeProfileForm(instance=instance)
    return render(request, "attendees/profile.html", {"form": form, "profile": instance})
