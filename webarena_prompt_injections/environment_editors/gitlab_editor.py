# Copyright (c) Meta Platforms, Inc. and affiliates.
import re
import os
import sys
from playwright.sync_api import TimeoutError, expect
from .base_environment_editor import BaseWebArenaEditor, WebArenaEditorException
from urllib.parse import urlparse, urlunparse


class GitlabEditor(BaseWebArenaEditor):
    """A class to automate actions on GitLab through a browser using Playwright.

    This class can log in to a GitLab instance and perform automated actions such as
    creating an issue. It manages a headless browser session using Playwright and
    stores authentication state to facilitate repeated actions.
    """

    def __init__(self, gitlab_domain: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.environment = "gitlab"
        self.gitlab_domain = gitlab_domain

    def login(self, username: str, password: str) -> bool:
        """Log in to the GitLab instance using provided credentials.

        Args:
            username (str): The GitLab username.
            password (str): The GitLab password.

        Returns:
            bool: True if login was successful, False otherwise.
        """
        self.page.goto(f"{self.gitlab_domain}/users/sign_in", wait_until="networkidle")

        self.page.set_viewport_size({"width": 1280, "height": 1500})

        try:
            self.page.wait_for_selector("input#user_login", timeout=10000)
        except:
            screenshot_path = "/tmp/debug_gitlabeditor_login_no_user_field.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to login. Did not find user input field {self.page.url}. Screenshot at {screenshot_path}"
            )

        self.page.fill("input#user_login", username)
        self.page.fill("input#user_password", password)

        try:
            with self.page.expect_navigation():
                self.page.click('button[type="submit"]')
        except TimeoutError:
            screenshot_path = "/tmp/debug_gitlabeditor_login.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to login. Screenshot at {screenshot_path}"
            )

        # check if survey page appeared after login (happens for new accounts)
        if "To personalize your GitLab experience" in self.page.content():
            try:
                self.page.select_option("#user_role", value="software_developer")
                with self.page.expect_navigation():
                    self.page.click('button:has-text("Get started!")')
            except Exception as e:
                print(
                    f"Unknown exception while responding to the survey after login {str(e)}",
                    file=sys.stderr,
                )

        if self.page.url.strip("/") != self.gitlab_domain:
            screenshot_path = "/tmp/debug_gitlabeditor_login.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to login. Actually navigated to {self.page.url}. Username: {username} Password {password}. Screenshot at {screenshot_path}"
            )

    def create_issue_with_title(
        self, project_owner: str, project_name: str, title_to_type_in: str
    ):
        """Create a new issue in a specified GitLab project by providing a title.

        Args:
            project_owner (str): The GitLab user or namespace that owns the project.
            project_name (str): The name of the project.
            title_to_type_in (str): The title of the new issue to be created.
        """
        url_of_action = (
            f"{self.gitlab_domain}/{project_owner}/{project_name}/-/issues/new"
        )
        self._simple_type_and_submit(
            url_of_action,
            "#issue_title",
            title_to_type_in,
            'button:has-text("Create issue")',
        )

    def create_issue_with_title_and_text(
        self,
        project_owner: str,
        project_name: str,
        title_to_type_in: str,
        text_of_issue: str,
    ):
        url_of_action = (
            f"{self.gitlab_domain}/{project_owner}/{project_name}/-/issues/new"
        )
        self.page.goto(url_of_action, wait_until="networkidle")

        self.page.fill(
            "#issue_title",
            title_to_type_in,
        )
        self.page.fill("textarea#issue_description", text_of_issue)

        try:
            with self.page.expect_navigation():
                self.page.click('button:has-text("Create issue")')
        except TimeoutError:
            screenshot_path = "/tmp/debug_gitlabeditor_login.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to create issue at {url_of_action}. Screenshot at {screenshot_path}"
            )

        issue_created_url_pattern = rf".*{project_owner}/{project_name}/-/issues/\d+$"

        if re.match(issue_created_url_pattern, self.page.url):
            return self.page.url
        else:
            screenshot_path = (
                "/tmp/debug_gitlabeditor_issue_creation_with_title_and_text.png"
            )
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Issue creation likely failed. Did not end up at an expected URL; instead at {self.page.url}. Screenshot for debugging at {screenshot_path}"
            )

    def delete_issue_given_url(
        self,
        url_of_issue: str,
    ):
        self.page.goto(url_of_issue, wait_until="networkidle")

        self.page.get_by_role("button", name="Issue actions").click()

        delete_issue_selector = '[data-qa-selector="delete_issue_button"]'

        # Wait for the dropdown to load
        self.page.wait_for_selector(delete_issue_selector, state="visible")
        self.page.locator(delete_issue_selector).click()

        # Wait for the confirmation modal to load
        self.page.wait_for_selector("div#delete-modal-id___BV_modal_body_")

        try:
            with self.page.expect_navigation():
                self.page.click('[data-qa-selector="confirm_delete_issue_button"]')

            self.page.wait_for_selector(
                'div.gl-alert-body:has-text("The issue was successfully deleted")',
                state="visible",
            )
        except Exception:
            screenshot_path = "/tmp/debug_delete_issue.png"
            self.page.screenshot(path=screenshot_path)
            print(
                f"Failed to delete issue at {url_of_issue}. Screenshot at {screenshot_path}, skipping...",
                file=sys.stderr,
            )

    def delete_all_issues_in_project(
        self, project_owner: str, project_name: str, max_timeout: float = 2000.0
    ):
        url_of_issues_page = (
            f"{self.gitlab_domain}/{project_owner}/{project_name}/-/issues"
        )
        self.page.goto(url_of_issues_page, wait_until="networkidle")

        issue_selector = "a[data-qa-selector='issuable_title_link']"

        # Extract title and URL of the first issue
        list_of_issues = self.page.locator(issue_selector)

        while list_of_issues.count() > 0:
            issue_url = list_of_issues.first.get_attribute("href")

            # Deal with bug in environment where issues point to different domain
            parsed_issue_url = urlparse(issue_url)
            updated_url = urlunparse(
                parsed_issue_url._replace(
                    netloc=self.gitlab_domain.strip("http://").strip("https://")
                )
            )

            self.delete_issue_given_url(updated_url)

            if self.page.url != url_of_issues_page:
                self.page.goto(url_of_issues_page, wait_until="networkidle")

            try:
                self.page.wait_for_selector(issue_selector, timeout=max_timeout)
            except TimeoutError:
                print(
                    f"Could not find any more issues at {url_of_issues_page}",
                    file=sys.stderr,
                )
                return

            list_of_issues = self.page.locator(issue_selector)
            print(
                f"Bulk deleting all issues in {project_owner}/{project_name}. Remaining {list_of_issues.count()} issues on {self.page.url}",
                file=sys.stderr,
            )

    def create_private_group(self, group_name):
        """
        Automates the creation of a private group in the GitLab group creation form.

        Args:
            group_name (str): The name of the group to be created.

        Returns:
            the slug name of the group (if it was created, based on the page GitLab redirected us to after creation);
            in case of clashes, this might have a number appended to the desired group_name
        """
        # Navigate to the group creation page
        self.page.goto(
            f"{self.gitlab_domain}/groups/new#create-group-pane",
            wait_until="networkidle",
        )

        # Wait for the group name field to be visible before filling
        self.page.locator("#group_name").wait_for(state="visible")

        # Fill in the "Group name"
        self.page.locator("#group_name").fill(group_name)

        # we will wait here since if there's a clash in the name of the group,
        # GitLab will populate the URL with the name with a number appended to it
        # if we do not wait, group creation proceeds and a clash occurs.
        self.page.wait_for_timeout(3000)

        # Select the "Private" radio button for visibility level
        self.page.locator("label[for='group_visibility_level_0']").check()

        # Select "Software Developer" from the Role dropdown
        self.page.locator("#user_role").select_option("software_developer")

        # Select "My company or team" radio button
        self.page.locator("label[for='group_setup_for_company_true']").click()

        # Select "I want to explore GitLab..." from the last dropdown
        self.page.locator("#group_jobs_to_be_done").select_option("exploring")

        try:
            with self.page.expect_navigation():
                self.page.get_by_role("button", name="Create group").click()
        except TimeoutError:
            screenshot_path = "/tmp/debug_gitlabeditor_group_creation.png"
            self.page.screenshot(path=screenshot_path)
            shared_message = f"Failed to create group '{group_name}' and ended up at {self.page.url}. Screenshot at {screenshot_path}"
            # If we are here, we did not up at the expected project page
            error_container = self.page.locator("div#error_explanation")
            if error_container.count() > 0:
                # Extract the error messages
                errors = error_container.locator("ul li").all_inner_texts()
                # Join them into a single message
                error_message = "; ".join(errors)

                raise WebArenaEditorException(
                    f"{shared_message} with the following errors: {error_message}"
                )
            else:
                # If there's no known error message, raise a generic exception
                raise WebArenaEditorException(
                    f"{shared_message} with no error messages found in the format we were expecting."
                )

        # Get the final URL after being redirected
        final_url = self.page.url
        parsed = urlparse(final_url)
        # The group path should be the last part of the URL path
        group_path = parsed.path.strip("/").split("/")[-1]

        return group_path

    def create_private_project(
        self, project_name, namespace_name=None, timeout_for_dropdown=5000
    ):
        """
        Automates the creation of a private project in GitLab using the project creation form.

         This method navigates to GitLab's "New Project" page, enters the specified project name,
         selects the given namespace (if multiple namespaces are available), sets the project
         to "Private" visibility, and submits the creation form. If creation succeeds, it returns
         the slug for the newly created project. If project creation fails, it raises an appropriate
         exception.

         Args:
             project_name (str): The name of the project to be created.
             namespace_name (str, optional): The name of the group or username (collectively: a namespace)
                 under which the project will be created. If not provided, the currently prefilled
                 namespace on the GitLab form will be used.
            timeout_for_dropdown (int, optional): The number of ms to wait for the dropdown selector of namespaces to appear;
                 increase this if the namespace exists but you are getting a ValueError due to the namespace not being available

         Returns:
             str: The slug name of the newly created project. Note that if the exact project name
             is taken, GitLab might append a numeric suffix to the slug.

         Raises:
             ValueError: If a specific namespace was requested but cannot be selected or does not match
                 the prefilled namespace on the page.
             GitLabProjectCreationFailureError: If the project could not be created due to known errors
                 returned by GitLab or unexpected conditions.
             TimeoutError: If navigation or form submission times out.
        """
        # Navigate to the project creation page
        self.page.goto(
            f"{self.gitlab_domain}/projects/new#blank_project", wait_until="networkidle"
        )

        # Fill in the project name
        name_locator = self.page.get_by_label("Project name")
        name_locator.wait_for(state="visible")
        name_locator.fill(project_name)

        # Wait briefly for JS-driven updates
        self.page.wait_for_timeout(2000)

        # Check for the presence of the button with id="__BVID__16__BV_toggle_"
        # (this button triggers the dropdown where namespaces can be selected)
        namespace_dropdown_button_selector = "button#__BVID__16__BV_toggle_"

        # Attempt to locate the toggle button on the page
        dropdown_button = self.page.locator(namespace_dropdown_button_selector)

        if dropdown_button.is_visible():
            # If the toggle button exists, we are on the page with multiple namespaces
            # and need to select the one we want from that dropdown
            # Click the dropdown button to reveal the group selection menu
            dropdown_button.click()

            # Wait for the dropdown to load
            self.page.wait_for_timeout(timeout_for_dropdown)

            # Select the desired group from the dropdown
            # Here we find the dropdown item that matches the given namespace_name
            group_item = self.page.locator(
                "li.gl-dropdown-item >> text={}".format(namespace_name)
            )

            if not group_item.is_visible():
                raise ValueError(
                    f"Unable to find namespace {namespace_name} in the dropdown. You might need to create it first or increase the timeout for waiting for the dropdown menu."
                )
            group_item.click()

        elif namespace_name is not None:
            prefilled_url_element = self.page.query_selector(
                ".input-group-prepend.static-namespace"
            )

            # Get the URL from the 'title' attribute
            prefilled_url = prefilled_url_element.get_attribute("title")
            parsed_url = urlparse(prefilled_url)
            prefilled_namespace_name = parsed_url.path.strip("/").split("/")[-1]

            if prefilled_namespace_name != namespace_name:
                # If the toggle button does not exist, we are on the page where namespace is pre-filled and not editable
                raise ValueError(
                    f"Namespace name {namespace_name} was requested for project creation but the selector for namespaces does not exist on the page and is prefilled with {prefilled_namespace_name}. Create the namespace first; this will likely get rid of this error."
                )
            # If they match, we do not need to raise an error as the user's intention is met
        # If the namespace name is not specified by the user, we will use the prefilled default, so no need to raise an error

        # Select the "Private" radio button for visibility level
        self.page.locator("#blank-project-pane").get_by_text(
            "PrivateProject access must be"
        ).check()

        try:
            with self.page.expect_navigation():
                self.page.get_by_role("button", name="Create project").click()

                # we end up here if there's a name collision
                if self.page.url.endswith("projects"):
                    raise WebArenaEditorException(
                        "Failed to end up at the expected URL"
                    )

        except (TimeoutError, WebArenaEditorException):
            screenshot_path = "/tmp/debug_gitlabeditor_project_creation.png"
            self.page.screenshot(path=screenshot_path)
            shared_message = f"Failed to create project '{project_name}' under '{namespace_name}' and ended up at {self.page.url}. Screenshot at {screenshot_path}"

            # If we are here, we did not up at the expected project page
            error_container = self.page.locator("div.project-edit-errors")
            if error_container.count() > 0:
                # Extract the error messages
                errors = error_container.locator("ul li").all_inner_texts()
                # Join them into a single message
                error_message = "; ".join(errors)
                if "taken" in error_message:
                    print(
                        f"Warning! It looks like the project {project_name} is already created. "
                        f"This is not an error but screenshot is still taken at {screenshot_path}. Proceeding to the next case...",
                        file=sys.stderr,
                    )
                    return project_name
                else:
                    raise WebArenaEditorException(
                        f"{shared_message} with the following errors: {error_message}"
                    )
            else:
                # If there's no known error message, raise a generic exception
                raise WebArenaEditorException(
                    f"{shared_message} with no error messages found in the format we were expecting."
                )

        final_url = self.page.url
        parsed = urlparse(final_url)
        # The group path should be the last part of the URL path
        project_slug = parsed.path.strip("/").split("/")[-1]
        return project_slug

    def create_user(self, first_name, last_name, username, email, password):
        """
        Automates the GitLab signup process.


        Args:
            first_name (str): The user's first name.
            last_name (str): The user's last name.
            username (str): The desired username.
            email (str): The user's email address.
            password (str): The desired password.
        """
        self.page.goto(f"{self.gitlab_domain}/users/sign_up", wait_until="networkidle")

        # Fill in the first name
        self.page.fill("#new_user_first_name", first_name)

        # Fill in the last name
        self.page.fill("#new_user_last_name", last_name)

        # Fill in the username
        self.page.fill("#new_user_username", username)

        # Fill in the email
        self.page.fill("#new_user_email", email)

        # Fill in the password
        self.page.fill("#new_user_password", password)

        def _shared_error_handling():
            screenshot_path = "/tmp/debug_gitlabeditor_user_creation.png"
            self.page.screenshot(path=screenshot_path)
            return f"Failed to register user '{username}' with first name {first_name} last name {last_name} with password '{password}' and email {email} and ended up at {self.page.url}. Screenshot at {screenshot_path}"

        try:
            with self.page.expect_navigation():
                self.page.click('[data-qa-selector="new_user_register_button"]')

            current_url = urlparse(self.page.url)
            expected_url_path = "users/sign_up/welcome"
            assert current_url.path.strip("/") == expected_url_path

        except TimeoutError:
            shared_error_message = _shared_error_handling()
            raise WebArenaEditorException(
                f"{shared_error_message} and navigation to welcome page timed out."
            )
        except AssertionError:
            shared_error_message = _shared_error_handling()
            # If we are here, we did not up at the expected project page
            error_container = self.page.locator("div#error_explanation")
            if error_container.count() > 0:
                # Extract the error messages
                errors = error_container.locator("ul li").all_inner_texts()
                # Join them into a single message
                error_message = "; ".join(errors)

                raise WebArenaEditorException(
                    f"{shared_error_message} with the following errors: {error_message}"
                )
            else:
                # If there's no known error message, raise a generic exception
                raise WebArenaEditorException(
                    f"{shared_error_message}  and did not end up at the welcome screen but had no error messages found in the format we were expecting."
                )

        self.page.select_option("#user_role", value="software_developer")

        with self.page.expect_navigation():
            self.page.click('input[type="submit"][value="Get started!"]')
        if self.page.url == self.gitlab_domain:
            shared_error_message = _shared_error_handling()
            raise WebArenaEditorException(
                f"{shared_error_message} at Welcome screen. Check screenshot and logs."
            )

    def add_user_to_group_as_maintainer(
        self, group_to_add_to: str, user_to_add: str, timeout_after_actions: int = 2000
    ):

        self.page.goto(
            f"{self.gitlab_domain}/groups/{group_to_add_to}/-/group_members",
            wait_until="networkidle",
        )

        def _get_exisiting_members():
            # Locate the table by its data-testid
            table_selector = "table[data-testid='members-table']"

            # Select all rows under the table body
            rows_selector = f"{table_selector} tbody tr"

            # Initialize an empty list to store account details
            accounts = []

            # Iterate through each row
            for row in self.page.query_selector_all(rows_selector):
                # Find the cell under the Account column (first column, index 0)
                account_cell = row.query_selector("td:nth-child(1)")

                if account_cell:
                    # Extract the display name
                    # name_element = account_cell.query_selector(".gl-avatar-labeled-label")
                    # name = name_element.inner_text().strip() if name_element else ""

                    # Extract the username
                    username_element = account_cell.query_selector(
                        ".gl-avatar-labeled-sublabel"
                    )
                    username = (
                        username_element.inner_text().strip()
                        if username_element
                        else ""
                    )

                    # Append the details as a dictionary
                    accounts.append(username.strip("@"))
            return accounts

        existing_accounts = _get_exisiting_members()

        if user_to_add in existing_accounts:
            print(
                f"User {user_to_add} was already a member of {group_to_add_to}",
                file=sys.stderr,
            )
            return

        self.page.click('button:has-text("Invite members")')

        # wait for the dialog to show up
        self.page.wait_for_selector(
            "#invite-members-modal-2___BV_modal_content_", state="visible"
        )

        # type in the username we want to add
        self.page.click("input#invite-members-modal-2_search")
        self.page.fill("input#invite-members-modal-2_search", user_to_add)

        self.page.wait_for_timeout(timeout_after_actions)

        dropdown_option_with_user_to_add = self.page.locator(
            f"ul.dropdown-menu li:has(span.gl-avatar-labeled-sublabel:text-is('{user_to_add}')) button"
        )
        dropdown_option_with_user_to_add.click()

        # 40 maps to the Maintainer role
        self.page.select_option("#invite-members-modal-2_dropdown", "40")

        self.page.wait_for_timeout(timeout_after_actions)

        self.page.click(
            '#invite-members-modal-2___BV_modal_content_ button:has-text("Invite")'
        )

        self.page.wait_for_selector(
            "div.gl-alert-body:has-text('Members were successfully added')",
            state="visible",
        )

        accounts_after_add = _get_exisiting_members()

        if not user_to_add in accounts_after_add:
            raise WebArenaEditorException(
                f"Failed to find {user_to_add} in {accounts_after_add} after addition"
            )

    def toggle_private_profile(self, desired_state_of_private_checkbox: bool):
        """
        Ensures that the 'Private profile' checkbox is checked. If it's not checked,
        the method ticks it, updates the profile settings, and verifies the change.

        Args:
            desired_state_of_private_checkbox (bool): if this is set to True,

        Raises:
            Exception: If any of the steps fail.
        """
        self.page.goto(f"{self.gitlab_domain}/-/profile")
        # Locate the Private profile checkbox
        checkbox_label_selector = "label[for='user_private_profile']"

        current_state_of_private_check = self.page.locator(
            checkbox_label_selector
        ).is_checked()

        if current_state_of_private_check != desired_state_of_private_checkbox:
            # Tick the checkbox
            if desired_state_of_private_checkbox:
                self.page.locator(checkbox_label_selector).check()
            else:
                self.page.locator(checkbox_label_selector).uncheck()

            # Click the "Update profile settings" button
            self.page.locator('button:has-text("Update profile settings")').click()

            # Wait for the success alert to appear
            try:
                success_alert_selector = (
                    "div.gl-alert.gl-alert-info[data-testid='alert-info']"
                )
                self.page.wait_for_selector(
                    f"{success_alert_selector} div.gl-alert-body:text('Profile was successfully updated')",
                    state="visible",
                )
                final_state_of_checkbox = self.page.locator(
                    checkbox_label_selector
                ).is_checked()
                assert final_state_of_checkbox == desired_state_of_private_checkbox
            except TimeoutError:
                raise WebArenaEditorException(
                    f"Unable to set private profile checkbox to {desired_state_of_private_checkbox}; success message did not appear."
                )
            except AssertionError:
                raise WebArenaEditorException(
                    f"Unable to set private profile checkbox to {desired_state_of_private_checkbox}; checkbox is in opposite state."
                )

    def delete_account(self, password: str):
        self.page.goto(
            f"{self.gitlab_domain}/-/profile/account", wait_until="networkidle"
        )

        delete_account_button_locator = 'button:has-text("Delete account")'
        delete_account_button_count = self.page.locator(
            delete_account_button_locator
        ).count()

        if delete_account_button_count < 1:
            delete_account_section = self.page.locator("text=Delete account").locator(
                "xpath=ancestor::div[contains(@class, 'row')]"
            )

            # Extract the text from the column next to 'Delete account'
            text_column = delete_account_section.locator(".col-lg-8")
            text = text_column.inner_text()
            raise WebArenaEditorException(
                f"Failed to delete account due to missing Delete Account button. The page had this error {text}"
            )

        self.page.click(delete_account_button_locator)

        # After clicking the button, a modal appears where the password needs to be confirmed
        password_confirmation_field_locator = (
            '[data-qa-selector="password_confirmation_field"]'
        )
        self.page.wait_for_selector(password_confirmation_field_locator, timeout=2000)
        self.page.locator(password_confirmation_field_locator).fill(password)

        try:
            with self.page.expect_navigation():
                self.page.locator(
                    '[data-qa-selector="confirm_delete_account_button"]'
                ).click()
        except TimeoutError:
            screenshot_path = "/tmp/debug_gitlabeditor_delete_account.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to delete account due to timeout, used password {password}. Screenshot at {screenshot_path}"
            )

        if self.page.url.strip("/") != f"{self.gitlab_domain}/users/sign_in":
            alert_locator = "div.gl-alert-body"
            alert_container_count = self.page.locator(alert_locator).count()
            if alert_container_count > 0:
                inner_text = self.page.locator(alert_locator).all_inner_texts()
                raise WebArenaEditorException(
                    f"Failed to delete account due to error {inner_text} and ended up at {self.page.url}, attempted with password {password}"
                )
            else:
                screenshot_path = "/tmp/debug_gitlabeditor_delete_account.png"
                self.page.screenshot(path=screenshot_path)
                raise WebArenaEditorException(
                    f"Failed to delete account due to unknown error and ended up at {self.page.url}, attempted with password {password}"
                )

        confirmation_page_text = (
            self.page.locator("div.gl-alert-body").text_content().strip()
        )
        if confirmation_page_text != "Account scheduled for removal.":
            screenshot_path = "/tmp/debug_gitlabeditor_delete_account.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Did not receive confirmation account was deleted. Screenshot at {screenshot_path}"
            )

    def _maybe_raise_page_not_found(self, url_of_action):
        possible_page_not_found_text_container = "div.container h3"
        if (self.page.locator(possible_page_not_found_text_container).count() > 0) and (
            self.page.locator(possible_page_not_found_text_container)
            .text_content()
            .strip()
            == "Page Not Found"
        ):
            raise WebArenaEditorException(
                f"Currently logged in user cannot access the page at {url_of_action}"
            )

    def _delete_project_or_group(
        self,
        url_of_action: str,
        confirmation_phrase: str,
        deletion_modal_trigger_button_text: str,
        deletion_confirmation_button_text: str,
        id_of_collapsed_section_with_delete_button: str,
        url_after_success: str,
    ):
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )
        try:
            self._maybe_raise_page_not_found(url_of_action)
        except WebArenaEditorException:
            print(
                f"Project page {url_of_action} not found, probably has already been deleted! ",
                file=sys.stderr,
            )
            return

        self.page.click(
            f'section#{id_of_collapsed_section_with_delete_button} button:has-text("Expand")'
        )

        delete_project_button_selector = (
            f'button:has-text("{deletion_modal_trigger_button_text}")'
        )

        try:
            self.page.wait_for_selector(delete_project_button_selector, timeout=1000)
        except TimeoutError:
            raise WebArenaEditorException(
                "Currently logged in user cannot access the deletion button"
            )

        self.page.locator(delete_project_button_selector).click()

        confirm_name_input_selector = "input#confirm_name_input"
        self.page.wait_for_selector(confirm_name_input_selector, timeout=1000)

        self.page.locator(confirm_name_input_selector).fill(confirmation_phrase)

        try:
            with self.page.expect_navigation():
                self.page.locator(
                    f'button:has-text("{deletion_confirmation_button_text}")'
                ).click()
        except TimeoutError:
            screenshot_path = "/tmp/debug_gitlabeditor_delete_project_or_group.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to delete project or group {confirmation_phrase} due to timeout. Screenshot at {screenshot_path}"
            )

        if self.page.url == url_after_success:
            confirmation_page_text = (
                self.page.locator("div.gl-alert-body").text_content().strip()
            )

            expected_confirmation_text = f"is in the process of being deleted."
            if not confirmation_page_text.endswith(expected_confirmation_text):
                screenshot_path = "/tmp/debug_gitlabeditor_delete_project_or_group.png"
                self.page.screenshot(path=screenshot_path)
                raise WebArenaEditorException(
                    f"Failed to delete project or group {confirmation_phrase}; expected confirmation text {expected_confirmation_text}, got {confirmation_page_text}. Screenshot at {screenshot_path}"
                )

    def delete_project(self, namespace_name: str, project_name: str):
        self._delete_project_or_group(
            url_of_action=f"{self.gitlab_domain}/{namespace_name}/{project_name}/edit",
            confirmation_phrase=f"{namespace_name}/{project_name}",
            deletion_modal_trigger_button_text="Delete project",
            deletion_confirmation_button_text="Yes, delete project",
            url_after_success=f"{self.gitlab_domain}/dashboard/projects",
            id_of_collapsed_section_with_delete_button="js-project-advanced-settings",
        )

    def delete_group(self, namespace_name: str):
        self._delete_project_or_group(
            url_of_action=f"{self.gitlab_domain}/groups/{namespace_name}/-/edit",
            confirmation_phrase=namespace_name,
            deletion_modal_trigger_button_text="Remove group",
            deletion_confirmation_button_text="Confirm",
            url_after_success=self.gitlab_domain,
            id_of_collapsed_section_with_delete_button="js-advanced-settings",
        )

    def _click_button_and_expect_navigation(self, button_selector, action_name):
        try:
            with self.page.expect_navigation():
                self.page.click(button_selector)
        except TimeoutError:
            screenshot_path = f"/tmp/debug_gitlabeditor_{action_name}.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"{action_name} fialed. Screenshot at {screenshot_path}"
            )

    def _wait_for_selector(self, button_selector, timeout=1000):
        try:
            self.page.wait_for_selector(button_selector, timeout=timeout)
        except TimeoutError:
            raise WebArenaEditorException(
                f"Timed out waiting for the button with selector {button_selector} on {self.page.url}"
            )

    def create_branch_in_project(
        self, namespace_name: str, project_name: str, branch_name: str
    ):
        """
        create a branch from main (does not modify the default selection of the from branch)
        in the specified project
        """
        url_of_action = (
            f"{self.gitlab_domain}/{namespace_name}/{project_name}/-/branches/new"
        )
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )

        self._maybe_raise_page_not_found(url_of_action)

        branch_name_field_selector = "input#branch_name"

        self.page.fill(branch_name_field_selector, branch_name)

        create_branch_button_selector = "#new-branch-form > div.form-actions > button"
        self._wait_for_selector(create_branch_button_selector)
        self._click_button_and_expect_navigation(
            create_branch_button_selector, "create_branch"
        )

    def create_empty_file_on_branch(
        self,
        namespace_name: str,
        project_name: str,
        branch_name: str,
        file_name: str,
    ):
        url_of_action = (
            f"{self.gitlab_domain}/{namespace_name}/{project_name}/-/new/{branch_name}"
        )

        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )

        self._maybe_raise_page_not_found(url_of_action)

        file_name_selector = "#file_name"

        self.page.fill(file_name_selector, file_name)

        create_file_button_selector = "#commit-changes"

        self._wait_for_selector(create_file_button_selector)
        self._click_button_and_expect_navigation(
            create_file_button_selector, "create_file"
        )

    def create_merge_request_from_branch(
        self,
        namespace_name: str,
        project_name: str,
        branch_name: str,
        merge_request_title: str,
    ):
        url_of_action = f"{self.gitlab_domain}/{namespace_name}/{project_name}/-/merge_requests/new?merge_request%5Bsource_branch%5D={branch_name}"
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )
        self._maybe_raise_page_not_found(url_of_action)

        error_container = self.page.locator("div#error_explanation")
        if error_container.count() > 0:
            # Extract the error messages
            errors = error_container.locator("ul li").all_inner_texts()
            # Join them into a single message
            error_message = "; ".join(errors)

            raise WebArenaEditorException(
                f"Could not create a merge request for branch {branch_name} due to the following errors: {error_message}"
            )

        merge_request_title_selector = "#merge_request_title"
        self.page.fill(merge_request_title_selector, merge_request_title)

        self._click_button_and_expect_navigation(
            "#new_merge_request > div.gl-mt-5.middle-block > button",
            "create_merge_request",
        )

        gitlab_domain_escaped = re.escape(self.gitlab_domain)
        namespace_name_escaped = re.escape(namespace_name)
        project_name_escaped = re.escape(project_name)
        # Build the pattern using string formatting
        merge_request_created_url_pattern = r"^{}/{}/{}/-/merge_requests/(\d+)$".format(
            gitlab_domain_escaped, namespace_name_escaped, project_name_escaped
        )

        match = re.match(merge_request_created_url_pattern, self.page.url)
        if match:
            return match.group(1)
        else:
            screenshot_path = "/tmp/debug_gitlabeditor_create_merge_request.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Likely failed to create merge request. Did not end up at an expected URL; instead at {self.page.url}. Screenshot for debugging at {screenshot_path}"
            )

    def close_merge_request(
        self, namespace_name: str, project_name: str, merge_request_number: int
    ):
        url_of_action = f"{self.gitlab_domain}/{namespace_name}/{project_name}/-/merge_requests/{merge_request_number}"
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )
        self._maybe_raise_page_not_found(url_of_action)

        close_merge_request_button_selector = "#notes > div.js-comment-form > ul > li > div > div > form > div.note-form-actions > button"
        self.page.click(close_merge_request_button_selector)

        merge_request_status_span_selector = "#content-body > div.merge-request > div.merge-request-details.issuable-details > div.detail-page-description.py-2.gl-display-flex.gl-align-items-center.gl-flex-wrap > span > span"
        try:
            expect(self.page.locator(merge_request_status_span_selector)).to_have_text(
                "Closed"
            )
        except TimeoutError:
            screenshot_path = "/tmp/debug_gitlabeditor_close_merge_request.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to clsoe merge request. Screenshot at {screenshot_path}"
            )

    def set_username_if_different(self, desired_username: str):
        self.page.goto(
            f"{self.gitlab_domain}/-/profile/account", wait_until="networkidle"
        )

        username_field_selector = "#username-change-input"
        prefilled_username = self.page.input_value(username_field_selector)
        if prefilled_username.strip() != desired_username:
            self.page.fill(username_field_selector, desired_username)
            first_confirm_button_selector = (
                '[data-testid="username-change-confirmation-modal"]'
            )
            self._wait_for_selector(first_confirm_button_selector)
            self.page.click(first_confirm_button_selector)

            second_confirm_button_selector = "#username-change-confirmation-modal___BV_modal_footer_ > button.btn.js-modal-action-primary.btn-confirm.btn-md.gl-button"
            self._wait_for_selector(second_confirm_button_selector, 10000)
            self.page.click(second_confirm_button_selector)

            try:
                self.page.wait_for_selector(
                    '[data-qa-selector="flash_container"]', timeout=10000
                )
                success_modal = self.page.locator(
                    "div", has_text="Username successfully changed"
                )

                if success_modal.count() < 1:
                    raise ValueError()
            except:
                screenshot_path = "/tmp/debug_gitlabeditor_change_username.png"
                self.page.screenshot(path=screenshot_path)
                raise WebArenaEditorException(
                    f"Failed to change username at {self.page.url}. Screenshot at {screenshot_path}"
                )

    def replace_file_with_local_file(
        self,
        namespace_name: str,
        project_name: str,
        branch_name: str,
        file_name: str,
        local_file_path: str,
    ):
        url_of_action = f"{self.gitlab_domain}/{namespace_name}/{project_name}/-/blob/{branch_name}/{file_name}"
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )

        trigger_replace_file_button_selector = '[data-testid="replace"]'

        self.page.click(trigger_replace_file_button_selector)

        upload_file_area_selector = "#modal-replace-blob___BV_modal_body_"

        self._wait_for_selector(upload_file_area_selector)
        self.page.locator('input[name="upload_file"]').set_input_files(local_file_path)

        replace_file_button_selector = "#modal-replace-blob___BV_modal_footer_ > button.btn.js-modal-action-primary.btn-confirm.btn-md.gl-button"
        self._wait_for_selector(replace_file_button_selector)
        self.page.click(replace_file_button_selector)

        self.page.wait_for_selector(
            "div.gl-alert-body:has-text('Your changes have been successfully committed')",
            state="visible",
        )

    def delete_branch(self, namespace_name: str, project_name: str, branch_name: str):
        url_of_action = (
            f"{self.gitlab_domain}/{namespace_name}/{project_name}/-/branches"
        )
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )

        # Define a selector for the branch item
        branch_selector = f'li.branch-item[data-name="{branch_name}"]'
        # Check if the branch exists in the active branches
        if self.page.locator(branch_selector).count() > 0:
            # Click the delete button for the branch
            self.page.locator(
                f"{branch_selector} button.js-delete-branch-button"
            ).click()
        else:
            screenshot_path = "/tmp/debug_gitlabeditor_delete_branch_notfound.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Branch '{branch_name}' not found in active branches at {self.page.url}."
            )

        confirm_delete_button = "#delete-branch-modal___BV_modal_footer_ > div > button.btn.btn-danger.btn-md.gl-button"
        self._wait_for_selector(confirm_delete_button)
        self.page.click(confirm_delete_button)

        try:
            alert_confirmation_selector = "#content-body > div.flash-container.flash-container-page.sticky > div > div > div"
            expect(self.page.locator(alert_confirmation_selector)).to_have_text(
                "Branch was deleted"
            )
        except TimeoutError:
            screenshot_path = "/tmp/debug_gitlabeditor_delete_branch.png"
            self.page.screenshot(path=screenshot_path)
            raise WebArenaEditorException(
                f"Failed to delete branch {branch_name}. Screenshot at {screenshot_path}"
            )

    def delete_deploy_key(self, namespace_name: str, project_name: str):
        url_of_action = (
            f"{self.gitlab_domain}/{namespace_name}/{project_name}/-/deploy_keys"
        )
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )
        btn_delete_selector = "#js-deploy-keys-settings > div.settings-content > div > div.deploy-keys-panel.table-holder > div.gl-responsive-table-row.deploy-key > div.table-section.section-15.table-button-footer.deploy-key-actions > div > button"
        confirm_delete_button = "#confirm-remove-deploy-key___BV_modal_footer_ > button.btn.js-modal-action-primary.btn-danger.btn-md.gl-button"
        try:
            self.page.wait_for_selector(btn_delete_selector, timeout=3000)
            button = self.page.query_selector(btn_delete_selector)
            # Click the button
            button.click()
            # Optionally, wait for some condition or delay if needed
            self.page.wait_for_timeout(1000)  # Wait for 1 second
            self._wait_for_selector(confirm_delete_button, timeout=3000)
            self.page.click(confirm_delete_button)
            self.page.wait_for_timeout(1000)  # Wait for 1 second
        except Exception as e:
            screenshot_path = "/tmp/debug_gitlabeditor_delete_deploykeys.png"
            self.page.screenshot(path=screenshot_path)
            print(
                f"[Warning] No Delete button or other error occurred: {e}. "
                f"Maybe deploy key is already deleted or do not exist. "
                f"Screenshot can be found at: {screenshot_path}",
                file=sys.stderr,
            )

    def delete_deploy_token(
        self, namespace_name: str, project_name: str, deploy_token_name: str
    ):
        url_of_action = f"{self.gitlab_domain}/{namespace_name}/{project_name}/-/settings/repository#js-deploy-tokens"
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )
        try:
            # Find the row containing the deploy token with the specified name
            row_selector = (
                f"table tbody tr:has(td:first-child:text-is('{deploy_token_name}'))"
            )
            self.page.wait_for_selector(row_selector, timeout=3000)

            # Find and click the revoke button in that specific row
            revoke_button_selector = (
                f"{row_selector} button[data-testid='revoke-button']"
            )
            self.page.wait_for_selector(revoke_button_selector, timeout=3000)
            self.page.click(revoke_button_selector)

            # Handle the confirmation dialog
            self.page.wait_for_timeout(1000)  # Wait for 1 second
            confirm_delete_button = "#revoke-modal-1___BV_modal_footer_ > a"
            self._wait_for_selector(confirm_delete_button, timeout=3000)
            self.page.click(confirm_delete_button)
            self.page.wait_for_timeout(1000)  # Wait for 1 second

        except Exception as e:
            screenshot_path = "/tmp/debug_gitlabeditor_delete_deploytokens.png"
            self.page.screenshot(path=screenshot_path)
            print(
                f"[Warning] No Delete button or other error occurred: {e}. "
                f"Maybe deploy token is already deleted or do not exist. "
                f"Screenshot can be found at: {screenshot_path}",
                file=sys.stderr,
            )

    def delete_webhook(self, namespace_name: str, project_name: str):
        url_of_action = f"{self.gitlab_domain}/{namespace_name}/{project_name}/-/hooks"
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )
        # btn_delete_selector = "#webhooks-index > div.gl-card-body.gl-py-0 > ul > li > div > div.col-md-4.col-lg-5.text-right-md.gl-mt-2 > a"
        btn_delete_selector = "a >> text=Delete"
        confirm_delete_button = "#confirmationModal___BV_modal_footer_ > button.btn.js-modal-action-primary.btn-danger.btn-md.gl-button"
        while True:
            try:
                self.page.wait_for_selector(btn_delete_selector, timeout=3000)
                button = self.page.query_selector(btn_delete_selector)
                # Click the button
                button.click()
                # Optionally, wait for some condition or delay if needed
                self.page.wait_for_timeout(1000)  # Wait for 1 second
                self._wait_for_selector(confirm_delete_button, timeout=3000)
                self.page.click(confirm_delete_button)
                self.page.wait_for_timeout(1000)  # Wait for 1 second
            except Exception as e:
                screenshot_path = "/tmp/debug_gitlabeditor_delete_webhook.png"
                self.page.screenshot(path=screenshot_path)
                print(
                    f"[Warning] No Delete button or other error occurred: {e}. "
                    f"Maybe webhook is already deleted or do not exist. "
                    f"Screenshot can be found at: {screenshot_path}",
                    file=sys.stderr,
                )
                break

    def delete_ssh_key(self):
        url_of_action = f"{self.gitlab_domain}/-/profile/keys"
        self.page.goto(url_of_action, wait_until="networkidle")
        btn_delete_selector = "#content-body > div.row.gl-mt-3.js-search-settings-section > div.col-lg-8 > div.gl-mb-3 > ul > li > div > span > div > div > button"
        confirm_delete_button = (
            "#confirm-modal-1___BV_modal_footer_ > button.btn.btn-danger"
        )
        try:
            self.page.wait_for_selector(btn_delete_selector, timeout=3000)
            button = self.page.query_selector(btn_delete_selector)
            # Click the button
            button.click()
            # Optionally, wait for some condition or delay if needed
            self.page.wait_for_timeout(1000)  # Wait for 1 second
            self._wait_for_selector(confirm_delete_button, timeout=3000)
            self.page.click(confirm_delete_button)
            self.page.wait_for_timeout(1000)  # Wait for 1 second
        except Exception as e:
            screenshot_path = "/tmp/debug_gitlabeditor_delete_sshkeys.png"
            self.page.screenshot(path=screenshot_path)
            print(
                f"[Warning] No Delete button or other error occurred: {e}. "
                f"Maybe ssh key is already deleted or do not exist. "
                f"Screenshot can be found at: {screenshot_path}",
                file=sys.stderr,
            )

    def delete_access_token(self):
        url_of_action = f"{self.gitlab_domain}/-/profile/personal_access_tokens"
        self.page.goto(
            url_of_action,
            wait_until="networkidle",
        )
        btn_delete_selector = "a[aria-label='Revoke']"
        confirm_delete_button = "#confirmationModal___BV_modal_footer_ > button.btn.js-modal-action-primary.btn-danger.btn-md.gl-button"
        while True:
            try:
                self.page.wait_for_selector(btn_delete_selector, timeout=3000)
                button = self.page.query_selector(btn_delete_selector)
                # Click the button
                button.click()
                # Optionally, wait for some condition or delay if needed
                self.page.wait_for_timeout(1000)  # Wait for 1 second
                self._wait_for_selector(confirm_delete_button, timeout=3000)
                self.page.click(confirm_delete_button)
                self.page.wait_for_timeout(1000)  # Wait for 1 second
            except Exception as e:
                screenshot_path = "/tmp/debug_gitlabeditor_delete_access_token.png"
                self.page.screenshot(path=screenshot_path)
                print(
                    f"[Warning] No Delete button or other error occurred: {e}. "
                    f"Maybe access token is already deleted or do not exist. "
                    f"Screenshot can be found at: {screenshot_path}",
                    file=sys.stderr,
                )
                break


if __name__ == "__main__":
    # Replace with actual values before running this script.
    GITLAB_DOMAIN = os.environ.get("GITLAB")
    USERNAME = "byteblaze"
    PASSWORD = "hello1234"
    PROJECT_OWNER = "byteblaze"
    PROJECT_NAME = "a11y-syntax-highlighting"
    ISSUE_TITLE = "This is a test issue created via Playwright automation"

    with GitlabEditor(GITLAB_DOMAIN, headless=True) as editor:
        # editor.create_user(
        #     "Hello5", "World", USERNAME, f"{USERNAME}@world.foo", PASSWORD
        # )
        editor.login(USERNAME, PASSWORD)
        print(f"Logged in as {USERNAME}")

        # print("attempting to delete deploy keys...")
        # editor.delete_deploy_key(USERNAME, "dotfiles")

        # print("Attempting to delete deploy tokens...")
        # editor.delete_deploy_token(USERNAME, "dotfiles")

        # print("Attempting to delete a webhook...")
        # editor.delete_webhook(USERNAME, "dotfiles")

        # print("Attempting to delete ssh key...")
        # editor.delete_ssh_key()

        print("Attempting to delete access tokens...")
        editor.delete_access_token()

        # editor.delete_branch(
        #     "a11yproject",
        #     "a11yproject.com",
        #     "special_feature_branch",
        # )

        # merge_request_number = editor.create_merge_request_from_branch(
        #     "a11yproject",
        #     "a11yproject.com",
        #     "special_feature_branch",
        #     "Fix critical bugs",
        # )
        # print(f"Opened merge request {merge_request_number}")

        # editor.close_merge_request(
        #     "a11yproject", "a11yproject.com", merge_request_number
        # )

        # print(f"Closed merge request {merge_request_number}")

        # editor.replace_file_with_local_file(
        #     "byteblaze",
        #     "dotfiles",
        #     "main",
        #     ".zshrc",
        #     "environment_editors/prisitine_dotfiles_zshrc.txt",
        # )
        # branch_name_for_test = "afifthbranch"
        # editor.create_branch_in_project("byteblaze", "dotfiles", branch_name_for_test)
        # editor.create_empty_file_on_branch(
        #     "byteblaze", "dotfiles", branch_name_for_test, "somefile"
        # )
        # editor.create_merge_request_from_branch(
        #     "byteblaze", "dotfiles", branch_name_for_test, "Fix critical bugs"
        # )

        # editor.delete_all_issues_in_project("byteblaze", "dotfiles")
        # print("Successfully deleted all issues.")
        # issue_url = editor.create_issue_with_title_and_text(
        #     PROJECT_OWNER, PROJECT_NAME, ISSUE_TITLE, f"{ISSUE_TITLE} but in the body"
        # )
        # print(f"Created issue with url {issue_url}")
        # editor.toggle_private_profile(False)
        # editor.delete_project("created_with_gitlabeditor", "created_project_with_gitlab_editor1")
        # editor.delete_group("created_with_gitlabeditor3")
        # print("Successfully deleted.")
        # editor.ensure_private_profile_enabled()
        # desired_group_name = "group_for_adding"
        # actual_group_identifier = editor.create_private_group(desired_group_name)
        # print(f"Group creation attempted with identifier {actual_group_identifier}.")
        # project_slug = editor.create_private_project("foo6", actual_group_identifier)
        # print(f"Project creation maybe succeeded with slug {project_slug}.")
        # editor.add_user_to_group_as_maintainer(actual_group_identifier, "byteblaze")
        # print(
        #     f"Succeeded in adding byteblaze to created_with_gitlabeditor52 owned by {USERNAME}"
        # )
