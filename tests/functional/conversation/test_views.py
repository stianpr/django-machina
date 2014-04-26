# -*- coding: utf-8 -*-

# Standard library imports
# Third party imports
from django.core.urlresolvers import reverse
from django.db.models import get_model
from guardian.shortcuts import assign_perm
from guardian.utils import get_anonymous_user

# Local application / specific library imports
from machina.apps.conversation.abstract_models import TOPIC_TYPES
from machina.apps.conversation.signals import topic_viewed
from machina.core.loading import get_class
from machina.test.factories import create_forum
from machina.test.factories import create_topic
from machina.test.factories import ForumReadTrackFactory
from machina.test.factories import PostFactory
from machina.test.factories import TopicReadTrackFactory
from machina.test.testcases import BaseClientTestCase
from machina.test.utils import mock_signal_receiver

ForumReadTrack = get_model('tracking', 'ForumReadTrack')
Post = get_model('conversation', 'Post')
Topic = get_model('conversation', 'Topic')
TopicReadTrack = get_model('tracking', 'TopicReadTrack')

PermissionHandler = get_class('permission.handler', 'PermissionHandler')


class TestTopicView(BaseClientTestCase):
    def setUp(self):
        super(TestTopicView, self).setUp()

        # Permission handler
        self.perm_handler = PermissionHandler()

        # Set up a top-level forum and a link forum
        self.top_level_forum = create_forum()

        # Set up a topic and some posts
        self.topic = create_topic(forum=self.top_level_forum, poster=self.user)
        self.post = PostFactory.create(topic=self.topic, poster=self.user)

        # Mark the forum as read
        ForumReadTrackFactory.create(forum=self.top_level_forum, user=self.user)

        # Assign some permissions
        assign_perm('can_read_forum', self.user, self.top_level_forum)

    def test_browsing_works(self):
        # Setup
        correct_url = self.topic.get_absolute_url()
        # Run
        response = self.client.get(correct_url, follow=True)
        # Check
        self.assertIsOk(response)

    def test_triggers_a_viewed_signal(self):
        # Setup
        correct_url = self.topic.get_absolute_url()
        # Run & check
        with mock_signal_receiver(topic_viewed) as receiver:
            self.client.get(correct_url, follow=True)
            self.assertEqual(receiver.call_count, 1)

    def test_increases_the_views_counter_of_the_topic(self):
        # Setup
        correct_url = self.topic.get_absolute_url()
        initial_views_count = self.topic.views_count
        # Run
        self.client.get(correct_url)
        # Check
        topic = self.topic.__class__._default_manager.get(pk=self.topic.pk)
        self.assertEqual(topic.views_count, initial_views_count + 1)

    def test_cannot_change_the_updated_date_of_the_topic(self):
        # Setup
        correct_url = self.topic.get_absolute_url()
        initial_updated_date = self.topic.updated
        # Run
        self.client.get(correct_url)
        # Check
        topic = self.topic.__class__._default_manager.get(pk=self.topic.pk)
        self.assertEqual(topic.updated, initial_updated_date)

    def test_marks_the_related_forum_as_read_if_no_other_unread_topics_are_present(self):
        # Setup
        new_topic = create_topic(forum=self.top_level_forum, poster=self.user)
        PostFactory.create(topic=new_topic, poster=self.user)
        TopicReadTrackFactory.create(topic=new_topic, user=self.user)
        TopicReadTrackFactory.create(topic=self.topic, user=self.user)
        PostFactory.create(topic=self.topic, poster=self.user)
        correct_url = self.topic.get_absolute_url()
        # Run
        self.client.get(correct_url)
        # Check
        forum_tracks = ForumReadTrack.objects.all()
        topic_tracks = TopicReadTrack.objects.all()
        self.assertEqual(forum_tracks.count(), 1)
        self.assertFalse(len(topic_tracks))
        self.assertEqual(forum_tracks[0].forum, self.topic.forum)
        self.assertEqual(forum_tracks[0].user, self.user)

    def test_marks_the_related_topic_as_read_if_other_unread_topics_are_present(self):
        # Setup
        new_topic = create_topic(forum=self.top_level_forum, poster=self.user)
        PostFactory.create(topic=new_topic, poster=self.user)
        PostFactory.create(topic=self.topic, poster=self.user)
        correct_url = self.topic.get_absolute_url()
        # Run
        self.client.get(correct_url)
        # Check
        topic_tracks = TopicReadTrack.objects.all()
        self.assertEqual(topic_tracks.count(), 1)
        self.assertEqual(topic_tracks[0].topic, self.topic)
        self.assertEqual(topic_tracks[0].user, self.user)

    def test_marks_the_related_topic_as_read_even_if_no_track_is_registered_for_the_related_forum(self):
        # Setup
        top_level_forum_alt = create_forum()
        topic_alt = create_topic(forum=top_level_forum_alt, poster=self.user)
        PostFactory.create(topic=topic_alt, poster=self.user)
        assign_perm('can_read_forum', self.user, top_level_forum_alt)
        correct_url = topic_alt.get_absolute_url()
        # Run
        self.client.get(correct_url)
        # Check
        forum_tracks = ForumReadTrack.objects.filter(forum=top_level_forum_alt)
        topic_tracks = TopicReadTrack.objects.all()
        self.assertEqual(forum_tracks.count(), 1)
        self.assertEqual(topic_tracks.count(), 0)

    def test_cannot_create_any_track_if_the_user_is_not_authenticated(self):
        # Setup
        ForumReadTrack.objects.all().delete()
        assign_perm('can_read_forum', get_anonymous_user(), self.top_level_forum)
        self.client.logout()
        correct_url = self.topic.get_absolute_url()
        # Run
        self.client.get(correct_url)
        # Check
        forum_tracks = ForumReadTrack.objects.all()
        topic_tracks = TopicReadTrack.objects.all()
        self.assertFalse(len(forum_tracks))
        self.assertFalse(len(topic_tracks))

    def test_can_paginate_based_on_a_post_id(self):
        # Setup
        for _ in range(0, 40):
            # 15 posts per page
            PostFactory.create(topic=self.topic, poster=self.user)
        correct_url = self.topic.get_absolute_url()
        # Run & check
        first_post_pk = self.topic.first_post.pk
        response = self.client.get(correct_url, {'post': first_post_pk}, follow=True)
        self.assertEqual(response.context_data['page_obj'].number, 1)
        mid_post_pk = self.topic.first_post.pk + 18
        response = self.client.get(correct_url, {'post': mid_post_pk}, follow=True)
        self.assertEqual(response.context_data['page_obj'].number, 2)
        last_post_pk = self.topic.last_post.pk
        response = self.client.get(correct_url, {'post': last_post_pk}, follow=True)
        self.assertEqual(response.context_data['page_obj'].number, 3)

    def test_properly_handles_a_bad_post_id_in_parameters(self):
        # Setup
        for _ in range(0, 40):
            # 15 posts per page
            PostFactory.create(topic=self.topic, poster=self.user)
        correct_url = self.topic.get_absolute_url()
        # Run & check
        bad_post_pk = self.topic.first_post.pk + 50000
        response = self.client.get(correct_url, {'post': bad_post_pk}, follow=True)
        self.assertEqual(response.context_data['page_obj'].number, 1)
        response = self.client.get(correct_url, {'post': 'I\'m a post'}, follow=True)
        self.assertEqual(response.context_data['page_obj'].number, 1)


class TestTopicCreateView(BaseClientTestCase):
    def setUp(self):
        super(TestTopicCreateView, self).setUp()

        # Permission handler
        self.perm_handler = PermissionHandler()

        # Set up a top-level forum and a link forum
        self.top_level_forum = create_forum()

        # Set up a topic and some posts
        self.topic = create_topic(forum=self.top_level_forum, poster=self.user)
        self.post = PostFactory.create(topic=self.topic, poster=self.user)

        # Mark the forum as read
        ForumReadTrackFactory.create(forum=self.top_level_forum, user=self.user)

        # Assign some permissions
        assign_perm('can_read_forum', self.user, self.top_level_forum)
        assign_perm('can_start_new_topics', self.user, self.top_level_forum)

    def test_browsing_works(self):
        # Setup
        correct_url = reverse('conversation:topic-create', kwargs={'forum_pk': self.top_level_forum.pk})
        # Run
        response = self.client.get(correct_url, follow=True)
        # Check
        self.assertIsOk(response)

    def test_embed_the_current_forum_into_the_context(self):
        # Setup
        correct_url = reverse('conversation:topic-create', kwargs={'forum_pk': self.top_level_forum.pk})
        # Run
        response = self.client.get(correct_url, follow=True)
        # Check
        self.assertEqual(response.context_data['forum'], self.top_level_forum)

    def test_can_detect_that_a_preview_should_be_done(self):
        # Setup
        correct_url = reverse('conversation:topic-create', kwargs={'forum_pk': self.top_level_forum.pk})
        post_data = {
            'subject': 'My topic',
            'content': '[b]This is my topic[/b]',
            'topic_type': TOPIC_TYPES.topic_post,
            'preview': 'Preview',
        }
        # Run
        response = self.client.post(correct_url, post_data, follow=True)
        # Check
        self.assertTrue(response.context_data['preview'])

    def test_redirects_to_topic_view_on_success(self):
        # Setup
        correct_url = reverse('conversation:topic-create', kwargs={'forum_pk': self.top_level_forum.pk})
        post_data = {
            'subject': 'My topic',
            'content': '[b]This is my topic[/b]',
            'topic_type': TOPIC_TYPES.topic_post,
        }
        # Run
        response = self.client.post(correct_url, post_data, follow=True)
        # Check
        topic_url = reverse(
            'conversation:topic',
            kwargs={'forum_pk': self.top_level_forum.pk, 'pk': response.context_data['topic'].pk})
        self.assertGreater(len(response.redirect_chain), 0)
        last_url, status_code = response.redirect_chain[-1]
        self.assertIn(topic_url, last_url)
