from django.core.exceptions import PermissionDenied, ValidationError

from core.models import AgronomistAssignment, ChatThread, Message, User


def owner_scope_for_user(user):
    if user.role == User.Role.OWNER:
        return user
    if user.role == User.Role.WORKER:
        return user.owner
    return None


def users_can_talk_in_owner_scope(owner, sender, recipient):
    if sender == recipient:
        return False
    allowed_ids = {owner.id}
    allowed_ids.update(User.objects.filter(role=User.Role.WORKER, owner=owner).values_list("id", flat=True))
    allowed_ids.update(
        AgronomistAssignment.objects.filter(owner=owner).values_list("agronomist_id", flat=True)
    )
    return sender.id in allowed_ids and recipient.id in allowed_ids


def get_available_contacts(user):
    if user.role == User.Role.OWNER:
        owner = user
        contacts = User.objects.filter(owner=owner, role=User.Role.WORKER)
        agronomists = User.objects.filter(client_links__owner=owner, role=User.Role.AGRONOMIST)
        return (contacts | agronomists).distinct()
    if user.role == User.Role.WORKER and user.owner_id:
        owner = user.owner
        contacts = User.objects.filter(pk=owner.pk)
        agronomists = User.objects.filter(client_links__owner=owner, role=User.Role.AGRONOMIST)
        return (contacts | agronomists).distinct()
    if user.role == User.Role.AGRONOMIST:
        owner_ids = AgronomistAssignment.objects.filter(agronomist=user).values_list("owner_id", flat=True)
        owners = User.objects.filter(id__in=owner_ids)
        workers = User.objects.filter(role=User.Role.WORKER, owner_id__in=owner_ids)
        return (owners | workers).distinct()
    return User.objects.none()


def list_threads(user):
    return (
        ChatThread.objects.filter(participants=user)
        .select_related("owner")
        .prefetch_related("participants", "messages")
        .order_by("-updated_at")
    )


def get_or_create_thread(sender, recipient, owner):
    if not users_can_talk_in_owner_scope(owner, sender, recipient):
        raise PermissionDenied("Cross-owner chat is not allowed")

    existing = None
    candidate_threads = (
        ChatThread.objects.filter(owner=owner, participants=sender)
        .filter(participants=recipient)
        .prefetch_related("participants")
        .order_by("-updated_at", "-pk")
    )
    for thread in candidate_threads:
        participant_ids = {participant.pk for participant in thread.participants.all()}
        if participant_ids == {sender.pk, recipient.pk}:
            existing = thread
            break
    if existing:
        return existing

    thread = ChatThread.objects.create(owner=owner)
    thread.participants.set([sender, recipient])
    return thread


def get_messages(user, thread_id):
    thread = ChatThread.objects.filter(pk=thread_id, participants=user).first()
    if not thread:
        raise PermissionDenied("Thread is not available")
    return thread, thread.messages.select_related("sender")


def send_message(sender, *, recipient=None, thread=None, owner=None, text="", context_type=None, context_id=None):
    text = (text or "").strip()
    if not text:
        raise ValidationError("Message is empty")
    if thread:
        if not thread.participants.filter(pk=sender.pk).exists():
            raise PermissionDenied("Thread is not available")
    else:
        thread = get_or_create_thread(sender, recipient, owner)

    msg = Message.objects.create(
        thread=thread,
        sender=sender,
        text=text,
        context_type=context_type or None,
        context_id=context_id or None,
    )
    thread.save(update_fields=["updated_at"])
    return msg
