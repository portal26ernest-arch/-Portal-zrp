import unittest

import messenger_adapters


class MessengerAdapterBoundaryTest(unittest.TestCase):
    def test_official_providers_are_unconfigured_without_injected_adapter(self):
        self.assertIsNone(messenger_adapters.adapter_for('telegram'))
        self.assertIsNone(messenger_adapters.adapter_for('max'))

    def test_unknown_provider_fails_closed(self):
        with self.assertRaises(ValueError):
            messenger_adapters.adapter_for('unofficial-web-session')

    def test_injected_official_adapter_is_selected_by_provider(self):
        adapter=object()
        self.assertIs(messenger_adapters.adapter_for('telegram',{'telegram':adapter}),adapter)


if __name__=='__main__':unittest.main()
