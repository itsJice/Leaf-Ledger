from seleniumbase import BaseCase
BaseCase.main(__name__, __file__)


class RecorderTest(BaseCase):
    def test_recording(self):
        self.open("https://www.vickerman.com/")
