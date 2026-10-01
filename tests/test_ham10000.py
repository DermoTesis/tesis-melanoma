import pytest

from melanoma.data.ham10000 import COLUMNS, MetadataError, load_metadata

HEADER = ",".join(COLUMNS)


def write_meta(tmp_path, rows):
    path = tmp_path / "meta.csv"
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_label_is_one_only_for_positive_classes(tmp_path):
    path = write_meta(tmp_path, ["L1,I2,mel,histo,50,male,back,x",
                                 "L1,I1,mel,histo,50,male,back,x",
                                 "L2,I3,bcc,histo,60,female,face,x"])
    meta = load_metadata(path)
    assert meta.image_id.tolist() == ["I1", "I2", "I3"]
    assert meta.label.tolist() == [1, 1, 0]
    assert load_metadata(path, positive_classes=["mel", "bcc"]).label.tolist() == [1, 1, 1]


@pytest.mark.parametrize("rows, message", [
    (["L1,I1,mel,histo,50,male,back,x", "L1,I2,nv,histo,50,male,back,x"], "más de un diagnóstico"),
    (["L1,I1,mel,histo,50,male,back,x", "L2,I1,nv,histo,50,male,back,x"], "image_id repetidos"),
    ([",I1,mel,histo,50,male,back,x"], "sin lesion_id"),
    (["L1,I1,scc,histo,50,male,back,x"], "desconocidos"),
])
def test_inconsistent_metadata_is_rejected(tmp_path, rows, message):
    with pytest.raises(MetadataError, match=message):
        load_metadata(write_meta(tmp_path, rows))


def test_md5_mismatch_is_rejected(tmp_path):
    path = write_meta(tmp_path, ["L1,I1,mel,histo,50,male,back,x"])
    with pytest.raises(MetadataError, match="md5"):
        load_metadata(path, expected_md5="0" * 32)
