"""SMS message parts: GSM-7 160/153 septets with two-septet extension characters, UCS-2 70/67 code units with
surrogate pairs, never split across parts."""

from django.test import SimpleTestCase

from apps.core.services.delivery_rates.rules.sms_parts import GSM_BASIC, GSM_EXTENSION, sms_encoding, sms_parts


class GsmTests(SimpleTestCase):
    def test_the_alphabet_has_127_characters_plus_10_extensions(self):
        self.assertEqual((len(GSM_BASIC), len(GSM_EXTENSION)), (127, 10))

    def test_single_and_multipart_boundaries(self):
        for length, parts in ((0, 1), (1, 1), (160, 1), (161, 2), (306, 2), (307, 3), (459, 3), (460, 4)):
            with self.subTest(length=length):
                self.assertEqual(sms_parts("a" * length), parts)

    def test_extension_characters_take_two_septets(self):
        self.assertEqual(sms_parts("€" * 80), 1)
        self.assertEqual(sms_parts("€" * 81), 2)
        self.assertEqual(sms_parts("a" * 159 + "{"), 2)

    def test_an_extension_character_is_not_split_across_parts(self):
        # 152 septets, then a two-septet character: it moves whole to the second part.
        self.assertEqual(sms_parts("a" * 152 + "[" + "a" * 151), 2)
        self.assertEqual(sms_parts("a" * 152 + "[" + "a" * 152), 3)

    def test_gsm_encoding(self):
        self.assertEqual(sms_encoding("Your code is 123456 @£$"), "GSM-7")


class Ucs2Tests(SimpleTestCase):
    def test_single_and_multipart_boundaries(self):
        for length, parts in ((70, 1), (71, 2), (134, 2), (135, 3)):
            with self.subTest(length=length):
                self.assertEqual(sms_parts("ж" * length), parts)

    def test_one_non_gsm_character_makes_the_whole_body_ucs2(self):
        self.assertEqual(sms_parts("a" * 69 + "ж"), 1)
        self.assertEqual(sms_parts("a" * 70 + "ж"), 2)
        self.assertEqual(sms_encoding("Привет"), "UCS-2")

    def test_surrogate_pairs_take_two_code_units(self):
        self.assertEqual(sms_parts("😀" * 35), 1)
        self.assertEqual(sms_parts("😀" * 36), 2)

    def test_a_surrogate_pair_is_not_split_across_parts(self):
        # 66 code units, then a pair: it moves whole to the second part.
        self.assertEqual(sms_parts("ж" * 66 + "😀" + "ж" * 65), 2)
        self.assertEqual(sms_parts("ж" * 66 + "😀" + "ж" * 66), 3)
