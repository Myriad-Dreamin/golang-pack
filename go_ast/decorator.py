from typing import Union


def use_file_mapping(maybe_wrapping_cls: Union[type, str], *args):
    if isinstance(maybe_wrapping_cls, str):
        args = (maybe_wrapping_cls,) + args

    def use_file_mapping_2step(wrapping_cls):
        class WrappedClass(wrapping_cls, object):

            __file_mapping_attrs = args

            def use_file_mapping(self, mp):
                pos_prop = getattr(self, 'pos', None)
                if pos_prop:
                    pos_prop.use_file_mapping(mp)
                if self.__file_mapping_attrs:
                    for prop_name in self.__file_mapping_attrs:
                        p = getattr(self, prop_name)
                        if isinstance(p, list):
                            for sp in p:
                                sp.use_file_mapping(mp)
                        elif p:
                            p.use_file_mapping(mp)

        WrappedClass.__name__ = wrapping_cls.__name__
        return WrappedClass

    if isinstance(maybe_wrapping_cls, str):
        return use_file_mapping_2step
    return use_file_mapping_2step(maybe_wrapping_cls)