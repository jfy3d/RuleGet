# -*- coding: utf-8 -*-
import face_recognition

import timeout_decorator
import logging

logger = logging.getLogger('app')


# 获取人脸位置
@timeout_decorator.timeout(25)
def get_face_pos(path):
    image = face_recognition.load_image_file(path)
    logger.info('face_recognition.load_image_file')
    # todo 偶尔卡住
    face_locations = face_recognition.face_locations(image, 2)
    logger.info(face_locations)
    if len(face_locations) == 0:
        return None
    _pos = {}
    for top, right, bottom, left in face_locations:
        _pos[str(bottom - top)] = (int((left + right) / 2), int((bottom + top) / 2))
    keys = sorted(_pos)
    keys.reverse()
    return _pos[str(max(keys))]


# 根据人脸位置计算缩略图截取区域
@timeout_decorator.timeout(30)
def get_crop_by_face(path, width, height, crop_w, crop_h):
    logger.info('get_crop_by_face')
    _loc = get_face_pos(path)
    if _loc is None:
        return None
    _x, _y = _loc
    _x_percent = _x / width
    _y_percent = _y / height

    if width / height > crop_w / crop_h:
        logger.info('www image')

        src_crop_w = int(height*crop_w/crop_h)
        src_crop_h = height
        _x_scale = _x * crop_h / height
        _w_scale = width * crop_h / height
        crop_y = 0
        if _x_percent < 0.33:
            print('left face')
            if _x_scale > crop_w / 2:
                crop_x = _x_scale - crop_w / 2
            else:
                crop_x = 0
        elif _x_percent > 0.67:
            print('right face', _w_scale, _x_scale, _x)
            if (_w_scale - _x_scale) > crop_w / 2:
                print('> . <')
                crop_x = _x_scale - crop_w / 2
            else:
                print('>> .', _w_scale, crop_w)
                crop_x = _w_scale - crop_w

        else:
            print('face mid', (_w_scale - crop_w)/2, (_x_scale - _w_scale/2))
            crop_x = int((_w_scale - crop_w)/2 + (_x_scale - _w_scale/2))
            if crop_x < 0:
                crop_x = 0
        crop_x = crop_x*(height/crop_h)
    else:
        print('hhh image')
        src_crop_h = int(width * crop_h / crop_w)
        src_crop_w = width
        _y_scale = _y * crop_w / width
        _h_scale = height * crop_w / width
        crop_x = 0
        if _y_percent < 0.33:
            print('top face', _y_scale, crop_h / 2)
            if _y_scale > crop_h / 2:
                crop_y = _y_scale - crop_h / 2
            else:
                crop_y = 0
        elif _y_percent > 0.66:
            print('bottom face', _x, _y)
            if (_h_scale - _y_scale) > crop_h / 2:
                crop_y = _y_scale - crop_h / 2
            else:
                crop_y = _h_scale - crop_h
        else:
            print('mid face', _h_scale, crop_h)
            crop_y = int((_h_scale - crop_h) / 2 + (_y_scale - _h_scale/2))
            if crop_y < 0:
                crop_y = 0
        crop_y = crop_y * (width / crop_w)

    return int(crop_x), int(crop_y), src_crop_w, src_crop_h
