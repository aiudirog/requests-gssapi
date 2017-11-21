#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for requests_gssapi."""

from mock import Mock, MagicMock, patch
from requests.compat import urlparse
import requests

import gssapi

import requests_gssapi
import unittest

# Note: we're not using the @mock.patch decorator:
# > My only word of warning is that in the past, the patch decorator hides
# > tests when using the standard unittest library.
# > -- sigmavirus24 in https://github.com/requests/requests-kerberos/issues/1

fake_init = Mock(return_value=None)
fake_creds = Mock(return_value="fake creds")
fake_resp = Mock(return_value="GSSRESPONSE")

# GSSAPI exceptions require a major and minor status code for their
# construction, so construct a *really* fake one
fail_resp = Mock(side_effect=gssapi.exceptions.GSSError(0, 0))

gssflags = [gssapi.RequirementFlag.mutual_authentication,
            gssapi.RequirementFlag.out_of_sequence_detection]
gssdelegflags = gssflags + [gssapi.RequirementFlag.delegate_to_peer]

class KerberosTestCase(unittest.TestCase):
    def setUp(self):
        """Setup."""
        fake_init.reset_mock()
        fake_resp.reset_mock()
        fail_resp.reset_mock()
        fake_creds.reset_mock()

    def tearDown(self):
        """Teardown."""
        pass

    def test_negotate_value_extraction(self):
        response = requests.Response()
        response.headers = {'www-authenticate': 'negotiate token'}
        self.assertEqual(
            requests_gssapi.gssapi_._negotiate_value(response),
            'token'
        )

    def test_negotate_value_extraction_none(self):
        response = requests.Response()
        response.headers = {}
        self.assertTrue(
            requests_gssapi.gssapi_._negotiate_value(response) is None
        )

    def test_force_preemptive(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            auth = requests_gssapi.HTTPKerberosAuth(force_preemptive=True)

            request = requests.Request(url="http://www.example.org")

            auth.__call__(request)

            self.assertTrue('Authorization' in request.headers)
            self.assertEqual(request.headers.get('Authorization'), 'Negotiate GSSRESPONSE')

    def test_no_force_preemptive(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            auth = requests_gssapi.HTTPKerberosAuth()

            request = requests.Request(url="http://www.example.org")

            auth.__call__(request)

            self.assertTrue('Authorization' not in request.headers)

    def test_generate_request_header(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response = requests.Response()
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            host = urlparse(response.url).hostname
            auth = requests_gssapi.HTTPKerberosAuth()
            self.assertEqual(
                auth.generate_request_header(response, host),
                "Negotiate GSSRESPONSE"
            )
            fake_init.assert_called_with(creds=None,
                                   name=gssapi.Name("HTTP@www.example.org"),
                                   flags=gssflags,
                                   usage="initiate")
            fake_resp.assert_called_with("token")

    def test_generate_request_header_init_error(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fail_resp):
            response = requests.Response()
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            host = urlparse(response.url).hostname
            auth = requests_gssapi.HTTPKerberosAuth()
            self.assertRaises(requests_gssapi.exceptions.KerberosExchangeError,
                auth.generate_request_header, response, host
            )
            fake_init.assert_called_with(usage="initiate",
                                   name=gssapi.Name("HTTP@www.example.org"),
                                   flags=gssflags, creds=None)

    def test_generate_request_header_step_error(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fail_resp):
            response = requests.Response()
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            host = urlparse(response.url).hostname
            auth = requests_gssapi.HTTPKerberosAuth()
            self.assertRaises(requests_gssapi.exceptions.KerberosExchangeError,
                auth.generate_request_header, response, host
            )
            fake_init.assert_called_with(usage="initiate",
                                   name=gssapi.Name("HTTP@www.example.org"),
                                   flags=gssflags, creds=None)
            fail_resp.assert_called_with("token")

    def test_authenticate_user(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {'www-authenticate': 'negotiate servertoken'}

            connection = Mock()
            connection.send = Mock(return_value=response_ok)

            raw = Mock()
            raw.release_conn = Mock(return_value=None)

            request = requests.Request()
            response = requests.Response()
            response.request = request
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            response.status_code = 401
            response.connection = connection
            response._content = ""
            response.raw = raw
            auth = requests_gssapi.HTTPKerberosAuth()
            r = auth.authenticate_user(response)

            self.assertTrue(response in r.history)
            self.assertEqual(r, response_ok)
            self.assertEqual(
                request.headers['Authorization'],
                'Negotiate GSSRESPONSE')
            connection.send.assert_called_with(request)
            raw.release_conn.assert_called_with()
            fake_init.assert_called_with(name=gssapi.Name("HTTP@www.example.org"),
                                   flags=gssflags, usage="initiate",
                                   creds=None)
            fake_resp.assert_called_with("token")

    def test_handle_401(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {'www-authenticate': 'negotiate servertoken'}

            connection = Mock()
            connection.send = Mock(return_value=response_ok)

            raw = Mock()
            raw.release_conn = Mock(return_value=None)

            request = requests.Request()
            response = requests.Response()
            response.request = request
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            response.status_code = 401
            response.connection = connection
            response._content = ""
            response.raw = raw
            auth = requests_gssapi.HTTPKerberosAuth()
            r = auth.handle_401(response)

            self.assertTrue(response in r.history)
            self.assertEqual(r, response_ok)
            self.assertEqual(
                request.headers['Authorization'],
                'Negotiate GSSRESPONSE')
            connection.send.assert_called_with(request)
            raw.release_conn.assert_called_with()
            fake_init.assert_called_with(creds=None,
                                   name=gssapi.Name("HTTP@www.example.org"),
                                   flags=gssflags, usage="initiate")
            fake_resp.assert_called_with("token")

    def test_authenticate_server(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {
                'www-authenticate': 'negotiate servertoken',
                'authorization': 'Negotiate GSSRESPONSE'}

            auth = requests_gssapi.HTTPKerberosAuth()
            auth.context = {"www.example.org": gssapi.SecurityContext}
            result = auth.authenticate_server(response_ok)

            self.assertTrue(result)
            fake_resp.assert_called_with("servertoken")

    def test_handle_other(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {
                'www-authenticate': 'negotiate servertoken',
                'authorization': 'Negotiate GSSRESPONSE'}

            auth = requests_gssapi.HTTPKerberosAuth()
            auth.context = {"www.example.org": gssapi.SecurityContext}

            r = auth.handle_other(response_ok)

            self.assertEqual(r, response_ok)
            fake_resp.assert_called_with("servertoken")

    def test_handle_response_200(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {
                'www-authenticate': 'negotiate servertoken',
                'authorization': 'Negotiate GSSRESPONSE'}

            auth = requests_gssapi.HTTPKerberosAuth()
            auth.context = {"www.example.org": gssapi.SecurityContext}

            r = auth.handle_response(response_ok)

            self.assertEqual(r, response_ok)
            fake_resp.assert_called_with("servertoken")

    def test_handle_response_200_mutual_auth_required_failure(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {}

            auth = requests_gssapi.HTTPKerberosAuth()
            auth.context = {"www.example.org": "CTX"}

            self.assertRaises(requests_gssapi.MutualAuthenticationError,
                              auth.handle_response,
                              response_ok)

            self.assertFalse(fake_resp.called)

    def test_handle_response_200_mutual_auth_required_failure_2(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fail_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {
                'www-authenticate': 'negotiate servertoken',
                'authorization': 'Negotiate GSSRESPONSE'}

            auth = requests_gssapi.HTTPKerberosAuth()
            auth.context = {"www.example.org": gssapi.SecurityContext}

            self.assertRaises(requests_gssapi.MutualAuthenticationError,
                              auth.handle_response,
                              response_ok)

            fail_resp.assert_called_with("servertoken")

    def test_handle_response_200_mutual_auth_optional_hard_failure(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fail_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {
                'www-authenticate': 'negotiate servertoken',
                'authorization': 'Negotiate GSSRESPONSE'}

            auth = requests_gssapi.HTTPKerberosAuth(
                requests_gssapi.OPTIONAL)
            auth.context = {"www.example.org": gssapi.SecurityContext}

            self.assertRaises(requests_gssapi.MutualAuthenticationError,
                              auth.handle_response,
                              response_ok)

            fail_resp.assert_called_with("servertoken")

    def test_handle_response_200_mutual_auth_optional_soft_failure(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200

            auth = requests_gssapi.HTTPKerberosAuth(
                requests_gssapi.OPTIONAL)
            auth.context = {"www.example.org": gssapi.SecurityContext}

            r = auth.handle_response(response_ok)

            self.assertEqual(r, response_ok)

            self.assertFalse(fake_resp.called)

    def test_handle_response_500_mutual_auth_required_failure(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fail_resp):
            response_500 = requests.Response()
            response_500.url = "http://www.example.org/"
            response_500.status_code = 500
            response_500.headers = {}
            response_500.request = "REQUEST"
            response_500.connection = "CONNECTION"
            response_500._content = "CONTENT"
            response_500.encoding = "ENCODING"
            response_500.raw = "RAW"
            response_500.cookies = "COOKIES"

            auth = requests_gssapi.HTTPKerberosAuth()
            auth.context = {"www.example.org": "CTX"}

            r = auth.handle_response(response_500)

            self.assertTrue(isinstance(r, requests_gssapi.gssapi_.SanitizedResponse))
            self.assertNotEqual(r, response_500)
            self.assertNotEqual(r.headers, response_500.headers)
            self.assertEqual(r.status_code, response_500.status_code)
            self.assertEqual(r.encoding, response_500.encoding)
            self.assertEqual(r.raw, response_500.raw)
            self.assertEqual(r.url, response_500.url)
            self.assertEqual(r.reason, response_500.reason)
            self.assertEqual(r.connection, response_500.connection)
            self.assertEqual(r.content, '')
            self.assertNotEqual(r.cookies, response_500.cookies)

            self.assertFalse(fail_resp.called)

            # re-test with error response sanitizing disabled
            auth = requests_gssapi.HTTPKerberosAuth(sanitize_mutual_error_response=False)
            auth.context = {"www.example.org": "CTX"}

            r = auth.handle_response(response_500)

            self.assertFalse(isinstance(r, requests_gssapi.gssapi_.SanitizedResponse))

    def test_handle_response_500_mutual_auth_optional_failure(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fail_resp):
            response_500 = requests.Response()
            response_500.url = "http://www.example.org/"
            response_500.status_code = 500
            response_500.headers = {}
            response_500.request = "REQUEST"
            response_500.connection = "CONNECTION"
            response_500._content = "CONTENT"
            response_500.encoding = "ENCODING"
            response_500.raw = "RAW"
            response_500.cookies = "COOKIES"

            auth = requests_gssapi.HTTPKerberosAuth(
                requests_gssapi.OPTIONAL)
            auth.context = {"www.example.org": "CTX"}

            r = auth.handle_response(response_500)

            self.assertEqual(r, response_500)

            self.assertFalse(fail_resp.called)

    def test_handle_response_401(self):
        # Get a 401 from server, authenticate, and get a 200 back.
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {'www-authenticate': 'negotiate servertoken'}

            connection = Mock()
            connection.send = Mock(return_value=response_ok)

            raw = Mock()
            raw.release_conn = Mock(return_value=None)

            request = requests.Request()
            response = requests.Response()
            response.request = request
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            response.status_code = 401
            response.connection = connection
            response._content = ""
            response.raw = raw

            auth = requests_gssapi.HTTPKerberosAuth()
            auth.handle_other = Mock(return_value=response_ok)

            r = auth.handle_response(response)

            self.assertTrue(response in r.history)
            auth.handle_other.assert_called_once_with(response_ok)
            self.assertEqual(r, response_ok)
            self.assertEqual(
                request.headers['Authorization'],
                'Negotiate GSSRESPONSE')
            connection.send.assert_called_with(request)
            raw.release_conn.assert_called_with()
            fake_init.assert_called_with(usage="initiate",
                                   name=gssapi.Name("HTTP@www.example.org"),
                                   flags=gssflags,
                                   creds=None)
            fake_resp.assert_called_with("token")

    def test_handle_response_401_rejected(self):
        # Get a 401 from server, authenticate, and get another 401 back.
        # Ensure there is no infinite recursion.
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            connection = Mock()

            def connection_send(self, *args, **kwargs):
                reject = requests.Response()
                reject.url = "http://www.example.org/"
                reject.status_code = 401
                reject.connection = connection
                return reject

            connection.send.side_effect = connection_send

            raw = Mock()
            raw.release_conn.return_value = None

            request = requests.Request()
            response = requests.Response()
            response.request = request
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            response.status_code = 401
            response.connection = connection
            response._content = ""
            response.raw = raw

            auth = requests_gssapi.HTTPKerberosAuth()

            r = auth.handle_response(response)

            self.assertEqual(r.status_code, 401)
            self.assertEqual(request.headers['Authorization'],
                             'Negotiate GSSRESPONSE')
            connection.send.assert_called_with(request)
            raw.release_conn.assert_called_with()
            fake_init.assert_called_with(usage="initiate",
                                   name=gssapi.Name("HTTP@www.example.org"),
                                   flags=gssflags,
                                   creds=None)
            fake_resp.assert_called_with("token")

    def test_generate_request_header_custom_service(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response = requests.Response()
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            host = urlparse(response.url).hostname
            auth = requests_gssapi.HTTPKerberosAuth(service="barfoo")
            auth.generate_request_header(response, host),
            fake_init.assert_called_with(usage="initiate",
                                   name=gssapi.Name("barfoo@www.example.org"),
                                   flags=gssflags,
                                   creds=None)
            fake_resp.assert_called_with("token")

    def test_delegation(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response_ok = requests.Response()
            response_ok.url = "http://www.example.org/"
            response_ok.status_code = 200
            response_ok.headers = {'www-authenticate': 'negotiate servertoken'}

            connection = Mock()
            connection.send = Mock(return_value=response_ok)

            raw = Mock()
            raw.release_conn = Mock(return_value=None)

            request = requests.Request()
            response = requests.Response()
            response.request = request
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            response.status_code = 401
            response.connection = connection
            response._content = ""
            response.raw = raw
            auth = requests_gssapi.HTTPKerberosAuth(1, "HTTP", True)
            r = auth.authenticate_user(response)

            self.assertTrue(response in r.history)
            self.assertEqual(r, response_ok)
            self.assertEqual(
                request.headers['Authorization'],
                'Negotiate GSSRESPONSE')
            connection.send.assert_called_with(request)
            raw.release_conn.assert_called_with()
            fake_init.assert_called_with(usage="initiate",
                                   name=gssapi.Name("HTTP@www.example.org"),
                                   flags=gssdelegflags,
                                   creds=None)
            fake_resp.assert_called_with("token")

    def test_principal_override(self):
        with patch.multiple("gssapi.Credentials", __new__=fake_creds), \
             patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response = requests.Response()
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            host = urlparse(response.url).hostname
            auth = requests_gssapi.HTTPKerberosAuth(principal="user@REALM")
            auth.generate_request_header(response, host)
            fake_creds.assert_called_with(gssapi.creds.Credentials,
                                          usage="initiate",
                                          name=gssapi.Name("user@REALM"))
            fake_init.assert_called_with(usage="initiate",
                                   name=gssapi.Name("HTTP@www.example.org"),
                                   flags=gssflags, creds="fake creds")
            fake_resp.assert_called_with("token")

    def test_realm_override(self):
        with patch.multiple("gssapi.SecurityContext", __init__=fake_init,
                            step=fake_resp):
            response = requests.Response()
            response.url = "http://www.example.org/"
            response.headers = {'www-authenticate': 'negotiate token'}
            host = urlparse(response.url).hostname
            auth = requests_gssapi.HTTPKerberosAuth(
                hostname_override="otherhost.otherdomain.org")
            auth.generate_request_header(response, host)
            fake_init.assert_called_with(
                usage="initiate",
                name=gssapi.Name("HTTP@otherhost.otherdomain.org"),
                flags=gssflags, creds=None)
            fake_resp.assert_called_with("token")


if __name__ == '__main__':
    unittest.main()
