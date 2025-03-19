# users/api.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Person, ExternalIdentity, AttributeChange

class PersonViewSet(viewsets.ModelViewSet):
    """
    API endpoint for people
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Person.objects.all().order_by('last_name', 'first_name')
    
    @action(detail=True)
    def identities(self, request, pk=None):
        """
        Get all external identities for a person
        """
        person = self.get_object()
        identities = person.external_ids.all()
        
        # Here you would serialize and return the identities
        return Response({'count': identities.count()})
    
    @action(detail=True)
    def changes(self, request, pk=None):
        """
        Get attribute change history for a person
        """
        person = self.get_object()
        changes = person.attribute_changes.all().order_by('-changed_at')
        
        # Here you would serialize and return the changes
        return Response({'count': changes.count()})