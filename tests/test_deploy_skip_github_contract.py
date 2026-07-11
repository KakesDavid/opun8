"""
Regression test for the deploy() <-> detect.py call contract.

Context: opun8.commands.detect._deploy_without_github() calls

    from opun8.commands.deploy import deploy as deploy_cmd
    deploy_cmd(platform_arg=None, skip_github=True)

deploy() didn't accept a skip_github argument, so choosing "Deploy
without GitHub" after re-detecting a folder crashed with:

    TypeError: deploy() got an unexpected keyword argument 'skip_github'

This test locks in that specific call contract: deploy() must accept
skip_github as a keyword argument, and when True it must skip the
interactive "with GitHub / without GitHub" menu and go straight to the
no-GitHub path. If a future refactor renames or removes this parameter,
this test fails here instead of in a user's terminal.
"""

import unittest
from unittest.mock import patch

from opun8.commands import deploy as deploy_mod


class TestDeploySkipGithubContract(unittest.TestCase):
    def setUp(self):
        # Isolate from real detection/auth/network for every test below.
        self.detect_patch = patch.object(
            deploy_mod, "_detect_project",
            return_value={"name": "demo", "type": "static"},
        )
        self.summary_patch = patch.object(deploy_mod, "_show_project_summary")
        self.detect_patch.start()
        self.summary_patch.start()
        self.addCleanup(self.detect_patch.stop)
        self.addCleanup(self.summary_patch.stop)

    def test_deploy_accepts_skip_github_keyword(self):
        """The exact call detect.py makes must not raise TypeError."""
        with patch.object(deploy_mod, "_deploy_without_github") as mock_no_gh:
            deploy_mod.deploy(platform_arg=None, skip_github=True)
        mock_no_gh.assert_called_once()

    def test_skip_github_true_bypasses_the_interactive_menu(self):
        """skip_github=True must never show the GitHub y/n menu."""
        with patch.object(deploy_mod, "_show_deploy_menu") as mock_menu, \
             patch.object(deploy_mod, "_deploy_without_github") as mock_no_gh:
            deploy_mod.deploy(skip_github=True)
        mock_menu.assert_not_called()
        mock_no_gh.assert_called_once()

    def test_skip_github_false_still_shows_the_interactive_menu(self):
        """Default behavior (no flag) must be unchanged."""
        with patch.object(deploy_mod, "_show_deploy_menu") as mock_menu:
            deploy_mod.deploy()
        mock_menu.assert_called_once()


if __name__ == "__main__":
    unittest.main()