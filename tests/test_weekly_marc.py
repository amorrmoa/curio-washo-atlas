"""Offline regression tests for NDL weekly MARC ingestion."""
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import weekly_marc as m

TAX = json.loads((Path(__file__).resolve().parents[1] / 'scripts/takayama_ja_taxonomy.json').read_text(encoding='utf-8'))


def tagged(ident='00123456', title='驚異の部屋と博物誌', pub='架空出版', publication='2026.11', status='n'):
    leader = f'00000{status}am a22     zi 4500'
    return '\n'.join([
        f'LDR                  {leader}',
        f'001                  {ident}',
        '008                  261110s2026    ja ||||g ||||f||||||jpn',
        f'020                  |a 9784123456789',
        f'24500                |a {title} / |c 編集者',
        f'264 1                |a 東京 : |b {pub}, |c {publication}',
        '650 7                |a 博物誌 |z 日本 |2 ndlsh',
    ]) + '\n'


def iso_record(ident='00123456', title='驚異の部屋と博物誌', status='n'):
    fields = [
        ('001', ident.encode('ascii') + b'\x1e'),
        ('008', b'261110s2026    ja ||||g ||||f||||||jpn\x1e'),
        ('245', b'00\x1fa' + title.encode('utf-8') + b'\x1e'),
        ('264', b' 1\x1fa\xe6\x9d\xb1\xe4\xba\xac\x1fb\xe6\x9e\xb6\xe7\xa9\xba\xe5\x87\xba\xe7\x89\x88\x1fc2026.11\x1e'),
        ('650', b' 7\x1fa\xe5\x8d\x9a\xe7\x89\xa9\xe8\xaa\x8c\x1e'),
    ]
    directory = b''
    fieldblock = b''
    for tag, value in fields:
        directory += tag.encode() + f'{len(value):04d}{len(fieldblock):05d}'.encode()
        fieldblock += value
    base = 24 + len(directory) + 1
    size = base + len(fieldblock) + 1
    leader = f'{size:05d}{status}am a22{base:05d}zi 4500'.encode('ascii')
    assert len(leader) == 24, leader
    return leader + directory + b'\x1e' + fieldblock + b'\x1d'


def zip_both(tagged_string=tagged(), marc_bytes=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        if marc_bytes is not None:
            archive.writestr('jmo202643.txt', marc_bytes)
        archive.writestr('jmo202643_confirmation.txt', tagged_string)
    return out.getvalue()


class TestWeeklyMarc(unittest.TestCase):
    def test_taxonomy_reuse(self):
        self.assertEqual(18, len(TAX['families']))
        self.assertEqual(43, len(TAX['queries']))

    def test_index_only_ms_archives(self):
        html = '<a href="/file/data/data_service/jnb_product/jmo202643.zip">2026年11月13日提供分</a> <a href="/file/data/data_service/jnb_product/jma202643.zip">典拠</a>'
        found = m.parse_index(html)
        self.assertEqual(1, len(found))
        self.assertEqual('2026-11-13', found[0]['date'])

    def test_tagged_parse_and_book(self):
        rec = list(m.parse_tagged(tagged()))[0]
        item = m.record_to_book(rec, '2026-11-13')
        self.assertEqual('驚異の部屋と博物誌', item['title'])
        self.assertEqual('2026-11', item['published'])
        self.assertEqual('架空出版', item['publisher'])
        self.assertIn('博物誌', item['subjects'])

    def test_zip_tagged_fallback(self):
        recs = m.records_from_zip(zip_both(marc_bytes=b'broken MARC'))
        self.assertEqual(1, len(recs))
        self.assertEqual('00123456', recs[0]['001'][0]['value'])

    def test_binary_marc(self):
        recs = list(m.parse_marc21(iso_record()))
        self.assertEqual('驚異の部屋と博物誌', m.record_to_book(recs[0])['title'])
        recs2 = m.records_from_zip(zip_both(marc_bytes=iso_record()))
        self.assertEqual(1, len(recs2))

    def test_score_strong_topic(self):
        score, tags = m.score_book({'title':'驚異の部屋と博物誌','subjects':'博物誌'}, TAX)
        self.assertGreaterEqual(score, m.MIN_SCORE)
        self.assertTrue(tags)

    def test_weak_fiction_excluded(self):
        score, _ = m.score_book({'title':'変身','subjects':''}, TAX)
        self.assertLess(score, m.MIN_SCORE)

    def test_update_deduplicate_and_delete(self):
        r1 = list(m.parse_tagged(tagged()))
        books, stat = m.apply_updates([], [('2026-11-13', r1)], TAX)
        self.assertEqual(1,len(books))
        self.assertEqual(1,stat['found_last_run'])
        books2, stat2 = m.apply_updates(books, [('2026-11-13', r1)], TAX)
        self.assertEqual(1,len(books2))
        self.assertEqual(0,stat2['found_last_run'])
        deletion = list(m.parse_tagged(tagged(status='d')))
        books3, _ = m.apply_updates(books2, [('2026-11-20', deletion)], TAX)
        self.assertEqual(0,len(books3))

    def test_pub_year_restriction(self):
        item=m.record_to_book(list(m.parse_tagged(tagged(publication='2022.3')))[0])
        self.assertFalse(m.valid_book(item))

    def test_per_publisher_max(self):
        blocks=[tagged(ident=f'0000{i:04d}',title=f'博物誌と怪物図像 {i}',pub='架空出版',publication='2026.11').replace('9784123456789', f'97841234567{i:02d}') for i in range(7)]
        recs=list(m.parse_tagged(''.join(blocks)))
        books, stat=m.apply_updates([], [('2026-11-13', recs)], TAX)
        self.assertEqual(2,len(books))
        self.assertEqual(2,stat['found_last_run'])


if __name__=='__main__': unittest.main()
