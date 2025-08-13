# Copyright (c) Meta Platforms, Inc. and affiliates.
import os
from playwright.sync_api import TimeoutError
from .base_environment_editor import BaseWebArenaEditor, WebArenaEditorException


class RedditEditor(BaseWebArenaEditor):
    def __init__(self, reddit_domain: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.environment = "reddit"
        self.reddit_domain = reddit_domain

    def login(self, username: str, password: str):
        """Log in to the Reddit instance using provided credentials.

        Args:
            username (str): The Reddit username.
            password (str): The Reddit password.
        """
        self.page.goto(f"{self.reddit_domain}/login", wait_until="networkidle")

        self.page.set_viewport_size({"width": 1280, "height": 1500})

        try:
            self.page.wait_for_selector("input#login-username", timeout=10000)
        except:
            screenshot_path = "/tmp/debug_redditeditor_login_no_user_field.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to login. Did not find user input field {self.page.url}. Screenshot at {screenshot_path}"
            )

        self.page.fill("input#login-username", username)
        self.page.fill("input#login-password", password)

        try:
            with self.page.expect_navigation():
                self.page.click('button[type="submit"]')
        except TimeoutError:
            screenshot_path = "/tmp/debug_redditeditor_login.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to login. Screenshot at {screenshot_path}"
            )

        if self.page.url.strip("/") != self.reddit_domain:
            screenshot_path = "/tmp/debug_redditeditor_login.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to login. Actually navigated to {self.page.url}. Username: {username} Password {password}. Screenshot at {screenshot_path}"
            )

    def create_user(self, first_name, last_name, username, email, password):
        """Creates a new Reddit account using provided credentials.

        Args:
            username (str): The new reddit username.
            password (str): The new reddit password.
        """
        start_url = f"{self.reddit_domain}/registration"
        self.page.goto(start_url, wait_until="networkidle")

        self.page.set_viewport_size({"width": 1280, "height": 720})

        try:
            self.page.wait_for_selector("input#user_username", timeout=10000)
        except:
            try:
                # trying to login
                self.login(username, password)
            except:
                screenshot_path = "/tmp/debug_redditeditor_signup_no_user_field.png"
                self.page.screenshot(path=screenshot_path)
                raise WebArenaEditorException(
                    f"Failed to sign up. Did not find user input field {self.page.url}. Screenshot at {screenshot_path}"
                )

        self.page.fill("input#user_username", username)
        self.page.fill("input#user_password_first", password)
        self.page.fill("input#user_password_second", password)

        try:
            with self.page.expect_navigation():
                self.page.click('button:has-text("Sign up")')
        except TimeoutError:
            screenshot_path = "/tmp/debug_redditeditor_signup.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to sign up. Screenshot at {screenshot_path}"
            )

        if (
            self.page.url.strip("/") == start_url
            and "This value is already used" in self.page.content()
        ):
            print(
                f"[Reddit Warning!] The account {username} has already been created! Trying to login..."
            )
            self.login(username, password)

    def create_post_with_title_and_text(
        self, forum: str, title_to_type_in: str, text_to_type_in: str, username: str
    ) -> str:
        """Create a new Reddit post with specific title and text.

        Args:
            forum (str): Forum name to post on (e.g. AskReddit).
            title_to_type_in (str): Title of the post.
            text_to_type_in (str): Text of the post.
            username: create a post on username's behalf
        """

        # first check if a post with this title has already been created
        self.page.goto(
            f"{self.reddit_domain}/user/{username}", wait_until="networkidle"
        )
        if title_to_type_in in self.page.content():
            link = self.page.query_selector(f"a:has-text('{title_to_type_in}')")
            if link:
                # Retrieve the href attribute
                href = link.get_attribute("href")
                print(
                    f"[Warning!] A post with title '{title_to_type_in}' already exists: {href}, skipping..."
                )
                return f"{self.reddit_domain}{href}"

        url_of_action = f"{self.reddit_domain}/submit"
        selector_title_to_type_in = "#submission_title"
        selector_text_to_type_in = "#submission_body"
        selector_forum = "#submission_forum"
        selector_of_submit_button = 'button:has-text("Create submission")'

        self.page.goto(url_of_action, wait_until="networkidle")

        try:
            self.page.wait_for_selector(selector_title_to_type_in, timeout=10000)
        except:
            screenshot_path = "/tmp/debug_redditeditor_notitlefiled.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"[WebArenaEditor] Form for creating a post not found. Screenshot at: {screenshot_path}"
            )
        self.page.fill(selector_title_to_type_in, title_to_type_in)
        self.page.fill(selector_text_to_type_in, text_to_type_in)
        self.page.select_option(selector_forum, forum)

        self.page.click(selector_of_submit_button)
        self.page.wait_for_load_state("networkidle")
        if self.page.url.strip("/") == url_of_action:
            screenshot_path = "/tmp/debug_redditeditor_creat_post.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to create a post. Screenshot at {screenshot_path}"
            )
        return self.page.url

    def create_forum(
        self,
        forum_name: str,
        forum_title: str,
        forum_description: str,
        forum_sidebar: str,
        username: str,
    ) -> str:
        """Create a new Reddit forum with specific name, title, description and sidebar."""

        # first check if a post with this title has already been created
        self.page.goto(
            f"{self.reddit_domain}/user/{username}", wait_until="networkidle"
        )
        if forum_name in self.page.content():
            link = self.page.query_selector(f"a:has-text('{forum_name}')")
            if link:
                # Retrieve the href attribute
                href = link.get_attribute("href")
                print(
                    f"[Warning!] A forum '{forum_name}' already exists: {href}, skipping..."
                )
                return f"{self.reddit_domain}{href}"

        url_of_action = f"{self.reddit_domain}/create_forum"
        selector_forum_name = "#forum_name"
        selector_title_to_type_in = "#forum_title"
        selector_descr_to_type_in = "#forum_description"
        selector_sidebar = "#forum_sidebar"
        selector_of_submit_button = 'button:has-text("Create forum")'

        self.page.goto(url_of_action, wait_until="networkidle")

        try:
            self.page.wait_for_selector(selector_forum_name, timeout=10000)
        except:
            screenshot_path = "/tmp/debug_redditeditor_noforumname.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"[WebArenaEditor] Form for creating a forum not found. Screenshot at: {screenshot_path}"
            )
        self.page.fill(selector_forum_name, forum_name)
        self.page.fill(selector_title_to_type_in, forum_title)
        self.page.fill(selector_descr_to_type_in, forum_description)
        self.page.fill(selector_sidebar, forum_sidebar)

        self.page.click(selector_of_submit_button)
        self.page.wait_for_load_state("networkidle")
        if self.page.url.strip("/") == url_of_action:
            screenshot_path = "/tmp/debug_redditeditor_create_forum.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to create a post. Screenshot at {screenshot_path}"
            )
        return self.page.url

    def block_user(self, username: str, username_to_block: str):
        """blocks username_to_block"""
        blocklist_url = f"{self.reddit_domain}/user/{username}/block_list"
        self.page.goto(blocklist_url, wait_until="networkidle")
        if username_to_block in self.page.content():
            print(
                f"[Warning!] A user '{username_to_block}' is already in block list, skipping..."
            )
            return self.page.url
        try:
            self.page.goto(
                f"{self.reddit_domain}/user/{username_to_block}/block_user",
                wait_until="networkidle",
            )
            selector_of_submit_button = 'button:has-text("Block")'
            self.page.click(selector_of_submit_button)
            self.page.wait_for_load_state("networkidle")
        except:
            screenshot_path = "/tmp/debug_redditeditor_blocklist_action.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to block a add {username_to_block} into {username}'s blocklist. "
                f"Make sure both usernames exist and login was performed! Screenshot at {screenshot_path}"
            )
        if self.page.url.strip("/") != blocklist_url:
            screenshot_path = "/tmp/debug_redditeditor_blocklist.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to block a add {username_to_block} into {username}'s blocklist. "
                f"Make sure both usernames exist and login was performed! Screenshot at {screenshot_path}"
            )
        return self.page.url

    def unblock_user(self, username: str, username_to_unblock: str):
        """Unblocks username_to_unblock from username's block list

        Args:
            username (str): The username who is doing the unblocking
            username_to_unblock (str): The username to be unblocked
        """
        blocklist_url = f"{self.reddit_domain}/user/{username}/block_list"
        self.page.goto(blocklist_url, wait_until="networkidle")

        # Check if the user to unblock is in the block list
        if username_to_unblock not in self.page.content():
            raise WebArenaEditorException(
                f"User '{username_to_unblock}' is not in block list at {blocklist_url}"
            )

        try:
            # Find the row that contains the username_to_unblock and get its unblock button
            unblock_button_selector = f"tr:has(a:has-text('{username_to_unblock}')) button:has-text('Unblock')"

            # Wait for the unblock button to be available
            self.page.wait_for_selector(unblock_button_selector, timeout=5000)

            # Click the unblock button
            self.page.click(unblock_button_selector)

            # Wait for the page to reload or update
            self.page.wait_for_load_state("networkidle")

            if username_to_unblock in self.page.content():
                screenshot_path = "/tmp/debug_redditeditor_unblock_failed.png"
                self.page.screenshot(path=screenshot_path)
                raise WebArenaEditorException(
                    f"Failed to unblock {username_to_unblock} from {username}'s blocklist. "
                    f"The user is still present in the block list. Screenshot at {screenshot_path}"
                )

        except Exception as e:
            screenshot_path = "/tmp/debug_redditeditor_unblock_action.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to unblock {username_to_unblock} from {username}'s blocklist: {str(e)} "
                f"Make sure both usernames exist and login was performed! Screenshot at {screenshot_path}"
            )

        return self.page.url

    def _upvote_or_downvote_post_by_url(
        self, url: str, selector: str, expected_vote_score: str
    ):
        def _error_handler(prepended_message=""):
            screenshot_path = "/tmp/debug_redditeditor_vote.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"{prepended_message} Failed to vote on a post at {url} with selector {selector}. Screenshot at {screenshot_path}"
            )

        # first check if a post with this title has already been created
        self.page.goto(url, wait_until="networkidle")

        try:
            self.page.wait_for_selector(
                selector,
                state="visible",
                timeout=2000,
            )

            # Click the button
            self.page.click(selector)

            self.page.wait_for_timeout(1000)  # Wait a bit for the vote to register

            # Find the span containing the vote score
            vote_score_selector = "#main > article.submission.submission--has-url.submission--has-body.submission--expanded.submission--visibility-visible > div > div.submission__vote > form > span.vote__net-score"

            try:
                # Wait for the score element to be available
                self.page.wait_for_selector(
                    vote_score_selector, state="visible", timeout=3000
                )

                # Get the vote score
                vote_score_element = self.page.query_selector(vote_score_selector)
                if vote_score_element:
                    vote_score = vote_score_element.inner_text().strip("'")
                    if vote_score != expected_vote_score:
                        _error_handler(
                            f"Expected vote score to be '{expected_vote_score}', but got '{vote_score}'"
                        )
                else:
                    _error_handler("Vote score element found but couldn't extract text")
            except Exception as e:
                _error_handler(f"Could not find vote score element: {e}")
        except Exception as e:
            _error_handler(f"No desired button or other error occurred: {e}")

    def upvote_post_by_url(self, url: str):
        self._upvote_or_downvote_post_by_url(
            url, "button.unbuttonize.vote__button.vote__up", "1"
        )

    def upvote_post_by_url_until_score(
        self,
        url: str,
        expected_vote_score: str,
    ):
        try:
            self._upvote_or_downvote_post_by_url(
                url, "button.unbuttonize.vote__button.vote__up", expected_vote_score
            )
        except WebArenaEditorException as e:
            if "Expected vote score to be" in str(e):
                print(
                    f"[Warning] Upvote failed: {e}. Retrying once to upvote until expected score is reached."
                )
                self._upvote_or_downvote_post_by_url(
                    url, "button.unbuttonize.vote__button.vote__up", expected_vote_score
                )
            else:
                raise e

    def downvote_post_by_url(self, url: str):
        self._upvote_or_downvote_post_by_url(
            url, "button.unbuttonize.vote__button.vote__down", "−1"
        )

    def delete_all_posts_by_username(self, username: str, max_attempts=5) -> str:
        """Deletes all reddit posts by username.

        Args:
            username: username whose posts should be deleted
        """

        self.page.goto(
            f"{self.reddit_domain}/user/{username}", wait_until="networkidle"
        )

        self.page.on("dialog", lambda dialog: dialog.accept())

        att_i = 0
        while att_i < max_attempts:
            try:
                self.page.wait_for_selector(
                    'button:has-text("Delete")', state="visible", timeout=3000
                )
                button = self.page.query_selector('button:has-text("Delete")')
                if not button:
                    break  # Exit the loop if no more buttons are found
                # Click the button
                button.click()
                # Optionally, wait for some condition or delay if needed
                self.page.wait_for_timeout(1000)  # Wait for 1 second
                att_i += 1
            except Exception as e:
                print(f"No Delete button or other error occurred: {e}")
                break  # Exit the loop if an error occurs

    def delete_post_by_url(self, url: str) -> str:
        """Create a new Reddit post with specific title and text.

        Args:
            url: url of the post to be deleted
        """

        # first check if a post with this title has already been created
        self.page.goto(f"{url}", wait_until="networkidle")

        self.page.on("dialog", lambda dialog: dialog.accept())

        try:
            self.page.wait_for_selector(
                'button:has-text("Delete")', state="visible", timeout=2000
            )
            button = self.page.query_selector('button:has-text("Delete")')
            # Click the button
            button.click()
            # Optionally, wait for some condition or delay if needed
            self.page.wait_for_timeout(1000)  # Wait for 1 second
        except Exception as e:
            print(f"No Delete button or other error occurred: {e}")

    def delete_user_post_by_title(
        self,
        user_username: str,
        title: str,
    ):
        """Deletes a specific post by the user with the given title

        Args:
            user_username: The username whose post should be deleted
            title: The title of the post to delete
        """
        user_posts_url = f"{self.reddit_domain}/user/{user_username}"
        self.page.goto(user_posts_url, wait_until="networkidle")

        # Find article containing the post with matching title
        post_selector = (
            f"article.submission:has(h1.submission__title:has-text('{title}'))"
        )
        self.page.wait_for_selector(post_selector, timeout=5000)

        # Find and click the delete button within that post
        delete_btn_selector = f"{post_selector} form[action*='delete'] button.fg-inherit.text-sm.unbuttonize"
        delete_btn = self.page.query_selector(delete_btn_selector)

        if delete_btn:
            # Handle confirmation dialog
            self.page.on("dialog", lambda dialog: dialog.accept())
            delete_btn.click()
            self.page.wait_for_timeout(1000)  # Wait for deletion to complete
        else:
            screenshot_path = "/tmp/debug_redditeditor_delete_post_by_title.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Delete button not found for post with title '{title}'. Screenshot at {screenshot_path}"
            )

    def delete_all_comments_on_post_by_user(self, url: str, max_attempts=5) -> str:
        """Deletes all comments by the user on the given post

        Args:
            url: url of the post where all user comments should be deleted
        """

        # first check if a post with this title has already been created
        self.page.goto(f"{url}", wait_until="networkidle")

        self.page.on("dialog", lambda dialog: dialog.accept())

        att_i = 0
        while att_i < max_attempts:
            try:
                self.page.wait_for_selector(
                    'button:has-text("Delete")', state="visible", timeout=3000
                )
                button = self.page.query_selector('button:has-text("Delete")')
                if not button:
                    break  # Exit the loop if no more buttons are found
                # Click the button
                button.click()
                # Optionally, wait for some condition or delay if needed
                self.page.wait_for_timeout(1000)  # Wait for 1 second
                att_i += 1
            except Exception as e:
                print(f"All comments are already deleted or other error occurred: {e}")
                break  # Exit the loop if an error occurs

    def delete_all_messages_by_user(self, username: str) -> str:
        """Deletes all comments by the user on the given post

        Args:
            url: url of the post where all user comments should be deleted
        """

        # first check if a post with this title has already been created
        url_msgs = f"{self.reddit_domain}/messages"
        self.page.goto(url_msgs, wait_until="networkidle")

        links = self.page.query_selector_all('a[href*="messages/thread"]')
        links = [link.get_attribute("href") for link in links]
        self.page.on("dialog", lambda dialog: dialog.accept())
        for link in links:
            try:
                href = f"{self.reddit_domain}{link}"
                # print(f"Visiting: {href}")
                self.page.goto(href, wait_until="networkidle")
                button = self.page.query_selector('button:has-text("Delete")')
                button.click()
            except Exception as e:
                screenshot_path = "/tmp/debug_redditeditor_deletemsg.png"
                self.page.screenshot(path=screenshot_path)
                print(
                    f"[Warning] Messages deleting failed: {e}. Screenshot at: {screenshot_path}"
                )

        return self.page.url

    def comment_on_post(self, subreddit: str, post_id: str, comment_text: str) -> str:
        """Create a new Reddit post with specific title and text.

        Args:
            subreddit (str): e.g. AskReddit, explainlikeimfive, etc
            post_id (str): ID of the post
            comment_text (str): body of the comment
        """
        url_of_action = f"{self.reddit_domain}/f/{subreddit}/{post_id}"
        selector_text_to_type_in = f"#reply_to_submission_{post_id}_comment"
        selector_of_submit_button = 'button:has-text("Post")'

        self.page.goto(url_of_action, wait_until="networkidle")

        try:
            self.page.wait_for_selector(selector_text_to_type_in, timeout=10000)
        except:
            screenshot_path = "/tmp/debug_redditeditor_nocommentfield.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"[WebArenaEditor] Form for commenting a post not found. Screenshot at: {screenshot_path}."
            )
        self.page.fill(selector_text_to_type_in, comment_text)

        self.page.click(selector_of_submit_button)
        self.page.wait_for_load_state("networkidle")
        if self.page.url.strip("/") == url_of_action:
            screenshot_path = "/tmp/debug_redditeditor_comment_post.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to comment on a post. Screenshot at {screenshot_path}"
            )
        return self.page.url

    def send_message(self, username_to_send: str, msg_content: str) -> str:
        """Create a new Reddit post with specific title and text.

        Args:
            username (str): reddit username to send a msg.
            msg_content (str): main body of the message.
        """
        self.page.goto(f"{self.reddit_domain}/messages", wait_until="networkidle")
        if (
            msg_content in self.page.content()
            and username_to_send in self.page.content()
        ):
            link = self.page.query_selector(f"a:has-text('{msg_content}')")
            if link:
                href = link.get_attribute("href")
                print(
                    f"[Warning!] A message with content '{msg_content}' to username {username_to_send} already exist, skipping..."
                )
                return f"{self.reddit_domain}{href}"

        url_of_action = f"{self.reddit_domain}/user/{username_to_send}/compose_message"
        selector_text_to_type_in = "#message_body"
        selector_of_submit_button = 'button:has-text("Send")'

        self.page.goto(url_of_action, wait_until="networkidle")

        try:
            self.page.wait_for_selector(selector_text_to_type_in, timeout=10000)
        except:
            self.page.screenshot(path="/tmp/debug_edit_submission.png")
            raise WebArenaEditorException(
                "[WebArenaEditor] Field to add the text not found. Taking a screenshot for debugging."
            )
        self.page.fill(selector_text_to_type_in, msg_content)
        self.page.click(selector_of_submit_button)
        self.page.wait_for_load_state("networkidle")

        if self.page.url.strip("/") == url_of_action:
            screenshot_path = "/tmp/debug_redditeditor_creat_post.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to send a msg. Screenshot at {screenshot_path}"
            )
        return self.page.url

    def reset_email(self, username: str) -> str:
        """
        Resets password to be empty string
        """
        self.page.goto(
            f"{self.reddit_domain}/user/{username}/account", wait_until="networkidle"
        )

        selector_email = "#user_email"
        selector_of_submit_button = 'button:has-text("Save changes")'

        try:
            self.page.wait_for_selector(selector_email, timeout=10000)
            self.page.fill(selector_email, "")
            self.page.click(selector_of_submit_button)
            self.page.wait_for_load_state("networkidle")
        except:
            screenshot_path = "/tmp/debug_redditeditor_resetemail.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"[WebArenaEditor] Form for resetting email error. Screenshot at: {screenshot_path}"
            )

        return self.page.url


if __name__ == "__main__":
    # Replace with actual values before running this script.
    REDDIT_DOMAIN = "http://3.146.174.90:9999"
    USERNAME = "MarvelsGrantMan136"
    PASSWORD = "test1234"
    NEW_USERNAME = "adv_user146"
    NEW_PASSWORD = "test12345"
    FORUM = "AskReddit"
    POST_TITLE = "Test title AAAAA5"
    POST_TEXT = "Test text BBBBBB"
    MSG_USER = "Interrete"
    MSG_TEXT = "Hi, how is it going? [AB123]"
    COMMENT_SUBREDDIT = "explainlikeimfive"
    COMMENT_POST_ID = "125342"
    COMMENT_TEXT = "OP is not telling the truth."
    NEW_FORUM_NAME = "test_forum146"
    USERNAME_TO_BLOCK = "astro_pettit"

    with RedditEditor(REDDIT_DOMAIN, headless=True) as editor:
        editor.login(USERNAME, PASSWORD)
        print(f"Logged in as {USERNAME}")
        editor.delete_user_post_by_title(
            USERNAME,
            "Inside Samuel",
        )
        # editor.unblock_user(USERNAME, "FrankTheBanker76")
        # editor.upvote_post_by_url_until_score(
        #     "http://3.23.69.150:9999/f/worldnews/136960/four-bankers-who-helped-putin-s-friend-set-up-swiss-bank",
        #     "1",
        # )
        # editor.delete_all_messages_by_user(USERNAME)

        # print(f"Creating a new username = {NEW_USERNAME}, with password: {NEW_PASSWORD}")
        # editor.create_user("", "", NEW_USERNAME, "", NEW_PASSWORD)
        # editor.login(NEW_USERNAME, NEW_PASSWORD)
        # print(f"Logged in as {NEW_USERNAME}")

        # editor.reset_email(NEW_USERNAME)

        # print(f"\nattempting to create a post with the title = {POST_TITLE} and text = {POST_TEXT} on forum = {FORUM}")
        # new_post_url = editor.create_post_with_title_and_text(FORUM, POST_TITLE, POST_TEXT, NEW_USERNAME)
        # print(f"Post was successfully created: {new_post_url}. Moving to the next test")

        # print(f"\nattempting to send a private msg: {MSG_TEXT} to the user: {MSG_USER}")
        # msg_thread_url = editor.send_message(MSG_USER, MSG_TEXT)
        # print(f"The message was successfully send: {msg_thread_url}. Moving to the next test")

        # print(f"\nattempting to comment with text: {COMMENT_TEXT} on a subreddit: {COMMENT_SUBREDDIT} with post id: {COMMENT_POST_ID}")
        # comment_url = editor.comment_on_post(COMMENT_SUBREDDIT, COMMENT_POST_ID, COMMENT_TEXT)
        # print(f"The message was successfully send: {comment_url}. Moving to the next test")

        # print(f"\nattempting to delete a post {new_post_url} by user: {NEW_USERNAME}")
        # editor.delete_post_by_url(new_post_url)
        # print(f"Post was deleted. Moving to the next test")

        # print(f"\nattempting to create a new forum {NEW_FORUM_NAME} by user: {NEW_USERNAME}")
        # new_forum_url = editor.create_forum(NEW_FORUM_NAME, NEW_USERNAME, NEW_FORUM_NAME, NEW_FORUM_NAME, NEW_USERNAME)
        # print(f"The forum was created: {new_forum_url}. Moving to the next test")

        # print(f"\nattempting to block a user {USERNAME_TO_BLOCK}")
        # blocklist_url = editor.block_user(NEW_USERNAME, USERNAME_TO_BLOCK)
        # print(f"Moving to the next test")

        # print(f"\nattempting to delete all posts by user: {NEW_USERNAME}")
        # editor.delete_all_posts_by_username(NEW_USERNAME)
        # print(f"All posts were deleted. Moving to the next test")
