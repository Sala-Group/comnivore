class MyCompose(object):
    def __init__(self, transforms):
        self.transforms = transforms

    def __call__(self, img):
        for i, t in enumerate(self.transforms):
            try:
                if t._get_name() == "Custom":
                    img = t(img)
                else:
                    img = t(img[0])
            except Exception as e:
                img = t(img)
        return img
    