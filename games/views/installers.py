"""Installer related API views"""
# pylint: disable=too-many-ancestors
from __future__ import absolute_import

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django.http import Http404
from rest_framework import generics, mixins, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from reversion.models import Version

from common.permissions import IsAdminOrReadOnly
from games import models, serializers

LOGGER = logging.getLogger(__name__)


class InstallerListView(generics.ListAPIView):
    """Return a list of all installers"""
    serializer_class = serializers.InstallerSerializer
    queryset = models.Installer.objects.all()


class InstallerDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Returns the details for a given installer accessed by its id"""
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = serializers.InstallerSerializer
    queryset = models.Installer.objects.all()

    def patch(self, request, *args, **kwargs):
        if request.data.get('published'):
            LOGGER.info("Installer is published by %s", self.request.user)
            request.data['published_by'] = self.request.user.id
        return super().patch(request, *args, **kwargs)


class GameInstallerListView(generics.ListAPIView):
    """Return the list of installers available for a game if a game slug is provided,
    or a particular installer if an installer slug is passed.
    """
    serializer_class = serializers.InstallerSerializer

    def get_queryset(self):
        slug = self.request.parser_context['kwargs']['slug']
        return models.Installer.objects.fuzzy_filter(slug)


class GameRevisionListView(generics.RetrieveAPIView):
    """Returns the list of revisions """
    permission_classes = [IsAdminUser]
    serializer_class = serializers.GameRevisionSerializer
    queryset = models.Game.objects.filter(change_for__isnull=True)
    lookup_field = 'slug'


class InstallerRevisionListView(generics.ListAPIView, mixins.DestroyModelMixin):
    """Return a list of revisions for a given installer"""
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = serializers.InstallerRevisionSerializer

    def get_queryset(self):
        installer = models.Installer.objects.get(pk=self.request.parser_context['kwargs']['pk'])
        return installer.revisions

    def delete(self, _request, *_args, **_kwargs):  # pylint: disable=no-self-use
        """Prevent deletion
        XXX Why is this needed?
        """
        return Response(status=status.HTTP_204_NO_CONTENT)


class InstallerRevisionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve a detailed view of an installer revision"""
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = serializers.InstallerRevisionSerializer

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except ObjectDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except ObjectDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if request.data.get('action') == 'accept':
            instance.accept(self.request.user)
            return Response(status=status.HTTP_202_ACCEPTED)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def get_object(self):
        try:
            version = Version.objects.get(pk=self.request.parser_context['kwargs']['pk'])
        except Version.DoesNotExist:
            raise Http404
        return models.InstallerRevision(version)


class InstallerIssueView(generics.ListAPIView, generics.CreateAPIView):
    """Returns all issues and their replies for a game"""
    serializer_class = serializers.InstallerIssueListSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        slug = self.request.parser_context['kwargs']['slug']
        game = models.Game.objects.get(slug=slug)
        return game.installers.all()


class InstallerIssueCreateView(generics.CreateAPIView):
    """Create a new issue"""
    serializer_class = serializers.InstallerIssueSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return the Installer instance based off URL parameters"""
        game_slug = self.request.parser_context['kwargs']['game_slug']
        installer_slug = self.request.parser_context['kwargs']['installer_slug']
        return models.Installer.objects.filter(game__slug=game_slug).get(slug=installer_slug)

    def create(self, request, *args, **kwargs): # pylint: disable=unused-argument
        """Create a new issue"""
        issue_payload = dict(request.data)

        # Complete the information with the current user
        issue_payload['submitted_by'] = request.user.id
        issue_payload['submitted_on'] = timezone.now()
        issue_payload['installer'] = self.get_queryset().id

        serializer = self.get_serializer(data=issue_payload)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class InstallerIssueReplyView(generics.CreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    """Edit or post a reply to an issue"""
    serializer_class = serializers.InstallerIssueSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        """Return the installer issue from its ID"""
        issue_id = self.request.parser_context['kwargs']['pk']
        return models.InstallerIssue.objects.get(pk=issue_id)

    def create(self, request, *args, **kwargs):  # pylint: disable=unused-argument
        """Create the reply"""
        issue_id = self.request.parser_context['kwargs']['pk']

        reply_payload = dict(request.data)
        # Complete the information with the current user
        reply_payload['submitted_by'] = request.user.id
        reply_payload['submitted_on'] = timezone.now()
        reply_payload['issue'] = issue_id

        serializer = serializers.InstallerIssueReplySerializer(data=reply_payload)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
