from itertools import combinations

import numpy
import pytest

from cogent3 import load_aligned_seqs, make_seq
from cogent3.core.annotation_db import GffAnnotationDb

from ensembl_lite._aligndb import (
    AlignDb,
    AlignRecord,
    GapPositions,
    get_alignment,
    write_alignments,
)
from ensembl_lite._convert import seq_to_gap_coords
from ensembl_lite._genomedb import CompressedGenomeSeqsDb, Genome


def small_seqs():
    from cogent3 import make_aligned_seqs

    seqs = {
        "s1": "GTTGAAGTAGTAGAAGTTCCAAATAATGAA",
        "s2": "GTG------GTAGAAGTTCCAAATAATGAA",
        "s3": "GCTGAAGTAGTGGAAGTTGCAAAT---GAA",
    }
    seqs = make_aligned_seqs(
        data=seqs,
        moltype="dna",
        array_align=False,
        info=dict(species=dict(s1="human", s2="mouse", s3="dog")),
    )
    annot_db = GffAnnotationDb(source=":memory:")
    annot_db.add_feature(
        seqid="s1", biotype="gene", name="not-on-s2", spans=[(4, 7)], on_alignment=False
    )
    annot_db.add_feature(
        seqid="s2",
        biotype="gene",
        name="includes-s2-gap",
        spans=[(2, 6)],
        on_alignment=False,
    )
    annot_db.add_feature(
        seqid="s3",
        biotype="gene",
        name="includes-s3-gap",
        spans=[(22, 27)],
        on_alignment=False,
    )
    seqs.annotation_db = annot_db
    return seqs


def make_records(start, end, block_id):
    aln = small_seqs()[start:end]
    records = []
    species = aln.info.species
    for seq in aln.seqs:
        seqid, seq_start, seq_end, seq_strand = seq.data.parent_coordinates()
        gs = seq.get_gapped_seq()
        c, s = seq_to_gap_coords(gs)
        record = AlignRecord(
            source="blah",
            species=species[seq.name],
            block_id=block_id,
            seqid=seqid,
            start=seq_start,
            stop=seq_end,
            strand="-" if seq_strand == -1 else "+",
            gap_spans=c,
        )
        records.append(record)
    return records


@pytest.fixture
def small_records():
    records = make_records(1, 5, "0")
    return records


def test_aligndb_records_match_input(small_records):
    import copy

    orig_records = copy.deepcopy(small_records)
    db = AlignDb(source=":memory:")
    db.add_records(records=small_records)
    got = list(db.get_records_matching(species="human", seqid="s1"))[0]
    for g, o in zip(got, orig_records):
        assert g == o


@pytest.mark.parametrize(
    "data",
    (
        "AB---CD--EF",
        "---ABCD--EF",
        "ABCD---EF--",
        "-----ABCDEF",
        "ABCDEF-----",
        "-ABCDEF----",
        "-A-B-C-D-EF",
        "A-B-C-D-EF-",
    ),
)
@pytest.mark.parametrize("index", range(4, 6))  # the ungapped sequence is 6 long
def test_gapped_convert_seq2aln(data, index):
    # converting a sequence index to alignment index
    ungapped = data.replace("-", "")
    seq = make_seq(data, moltype="text")
    g, s = seq_to_gap_coords(seq)
    gaps = GapPositions(g, len(seq))
    idx = gaps.from_seq_to_align_index(index)
    assert data[idx] == ungapped[index]


@pytest.mark.parametrize(
    "data",
    (
        "AB---CD--EF",
        "---ABCD--EF",
        "ABCD---EF--",
        "-----ABCDEF",
        "ABCDEF-----",
        "-ABCDEF----",
        "-A-B-C-D-EF",
        "A-B-C-D-EF-",
    ),
)
@pytest.mark.parametrize("index", range(6))  # the ungapped sequence is 6 long
def test_gapped_convert_seq2aln2seq(data, index):
    # round tripping seq to alignment to seq indices
    seq = make_seq(data, moltype="text")
    g, s = seq_to_gap_coords(seq)
    gaps = GapPositions(g, len(seq))
    align_index = gaps.from_seq_to_align_index(index)
    got = gaps.from_align_to_seq_index(align_index)
    assert got == index


@pytest.mark.parametrize(
    "data",
    (
        "AB--CDE-FG",
        "--ABC-DEFG",
        "AB--CDE-FG--",
        "ABCDE--FG---",
        "-----ABCDEFG",
        "-A-B-C-D-E-F-G-",
    ),
)
@pytest.mark.parametrize("seq_index", range(7))
def test_gapped_convert_aln2seq_nongap_char(data, seq_index):
    # test alignment indexes when aligned position is NOT a gap
    ungapped = "ABCDEFG"
    align_index = data.find(ungapped[seq_index])
    seq = make_seq(data, moltype="text")
    g, s = seq_to_gap_coords(seq)
    gaps = GapPositions(g, len(seq))
    idx = gaps.from_align_to_seq_index(align_index)
    assert idx == seq_index


def _find_nth_gap_index(data: str, n: int) -> int:
    num = -1
    for i, c in enumerate(data):
        if c == "-":
            num += 1
        if num == n:
            return i
    raise ValueError(f"{data=}, {n=}")


def _get_expected_seqindex(data: str, align_index: int) -> int:
    # compute the expected seqindex
    refseq = data.replace("-", "")
    got = data[align_index:].lstrip("-")
    return refseq.find(got[0]) if got else len(refseq)


@pytest.mark.parametrize(
    "data",
    (
        "AB-----CDE-F--G",
        "----ABC-DEFG---",
        "AB--CDE-FG-----",
        "ABCDE--FG------",
        "--------ABCDEFG",
        "-A-B-C-D-E-F-G-",
    ),
)
@pytest.mark.parametrize("gap_number", range(8))
def test_gapped_convert_aln2seq_gapchar(data, gap_number):
    # test alignment indexes when aligned position IS a gap
    # in this case we expect the position of the next non-gap
    # to be the result
    # find the alignment index corresponding to the
    align_index = _find_nth_gap_index(data, gap_number)
    assert data[align_index] == "-", (data, gap_number)
    # find nearest non-gap
    seq_index = _get_expected_seqindex(data, align_index)
    seq = make_seq(data, moltype="text")
    g, s = seq_to_gap_coords(seq)
    gaps = GapPositions(g, len(seq))
    idx = gaps.from_align_to_seq_index(align_index)
    assert idx == seq_index


def test_gapped_convert_aln2seq_invalid():
    seq = make_seq("AC--GTA-TG", moltype="dna")
    g, s = seq_to_gap_coords(seq)
    gaps = GapPositions(g, len(seq))
    with pytest.raises(NotImplementedError):
        gaps.from_align_to_seq_index(-1)


# fixture to make synthetic GenomeSeqsDb and alignment db
# based on a given alignment
@pytest.fixture
def genomedbs_aligndb(small_records):
    align_db = AlignDb(source=":memory:")
    align_db.add_records(records=small_records)
    seqs = small_seqs().degap()
    species = seqs.info.species
    data = seqs.to_dict()
    genomes = {}
    for name, seq in data.items():
        genome = CompressedGenomeSeqsDb(source=":memory:", species=name)
        genome.add_records(records=[(name, seq)])
        genomes[species[name]] = Genome(seqs=genome, annots=None, species=species[name])

    return genomes, align_db


def test_building_alignment(genomedbs_aligndb, namer):
    genomes, align_db = genomedbs_aligndb
    got = list(
        get_alignment(align_db, genomes, ref_species="mouse", seqid="s2", namer=namer)
    )[0]
    orig = small_seqs()[1:5]
    assert got.to_dict() == orig.to_dict()


@pytest.mark.parametrize(
    "kwargs",
    (dict(ref_species="dodo", seqid="s2"),),
)
def test_building_alignment_invalid_details(genomedbs_aligndb, kwargs):
    genomes, align_db = genomedbs_aligndb
    with pytest.raises(ValueError):
        list(get_alignment(align_db, genomes, **kwargs))


@pytest.mark.parametrize(
    "invalid_slice",
    (slice(None, None, -1), slice(None, -1, None), slice(-1, None, None)),
)
def test_gap_pos_invalid_slice(invalid_slice):
    gp = GapPositions(numpy.array([[1, 3]], dtype=numpy.int32), 20)
    with pytest.raises(NotImplementedError):
        gp[invalid_slice]


@pytest.mark.parametrize(
    "slice",
    (
        slice(3, 7),
        slice(20, None),
    ),
)
def test_no_gaps_in_slice(slice):
    # aligned length is 25
    seq_length = 20
    gap_length = 5
    gp = GapPositions(
        gaps=numpy.array([[10, gap_length]], dtype=numpy.int32), seq_length=seq_length
    )
    got = gp[slice]
    assert not len(got.gaps)
    start = slice.start or 0
    stop = slice.stop or (seq_length + gap_length)
    assert len(got) == stop - start


def test_len_gapped():
    seq_length = 20
    gap_length = 5

    gp = GapPositions(
        gaps=numpy.array([[10, gap_length]], dtype=numpy.int32), seq_length=seq_length
    )
    assert len(gp) == (seq_length + gap_length)


def test_all_gaps_in_slice():
    # slicing GapPositions
    # sample seq 1
    data = "AC--GTA-TG"
    seq = make_seq(data, moltype="dna")
    g, s = seq_to_gap_coords(seq)
    gp = GapPositions(g, len(data.replace("-", "")))
    sl = slice(1, 9)

    got = gp[sl]
    expect_gaps, expect_seq = seq_to_gap_coords(make_seq(data[sl], moltype="dna"))
    assert (got.gaps == expect_gaps).all()
    assert got.seq_length == 5


@pytest.mark.parametrize(
    "data",
    (
        "----GTA-TG",
        "AC--GTA---",
        "AC--GTA-TG",
        "A-C-G-T-A-",
        "-A-C-G-T-A",
        "ACGTAACGTA",
        "----------",
    ),
)
@pytest.mark.parametrize(
    "slice",
    [slice(i, j) for i, j in combinations(range(10), 2)],
)
def test_variant_slices(data, slice):
    seq = make_seq(data, moltype="dna")
    g, s = seq_to_gap_coords(seq)
    gaps = GapPositions(g, len(s))
    orig = gaps.gaps.copy()
    got = gaps[slice]

    expect_gaps, expect_seq = seq_to_gap_coords(make_seq(data[slice], moltype="dna"))
    assert got.seq_length == len(expect_seq)
    assert (got.gaps == expect_gaps).all()
    # make sure original data unmodified
    assert (orig == gaps.gaps).all()


def make_sample(two_aligns=False):
    aln = small_seqs()
    species = aln.info.species
    # make annotation db's
    annot_dbs = {}
    for name in aln.names:
        feature_db = aln.annotation_db.subset(seqid=name)
        annot_dbs[name] = feature_db

    # we will reverse complement the s2 genome compared to the original
    # this means our coordinates for alignment records from that genome
    # also need to be rc'ed
    genomes = {}
    for seq in aln.seqs:
        name = seq.name
        seq = seq.data.degap()
        if seq.name == "s2":
            seq = seq.rc()
            s2_genome = str(seq)
        genome = CompressedGenomeSeqsDb(source=":memory:", species=species[seq.name])
        genome.add_records(records=[(name, str(seq))])
        genomes[species[name]] = Genome(
            seqs=genome, annots=annot_dbs[name], species=species[name]
        )

    # define two alignment blocks that incorporate features
    align_records = _update_records(s2_genome, aln, "0", 1, 12)
    if two_aligns:
        align_records += _update_records(s2_genome, aln, "1", 22, 30)
    align_db = AlignDb(source=":memory:")
    align_db.add_records(records=align_records)

    return genomes, align_db


def _update_records(s2_genome, aln, block_id, start, end):
    # start, stop are the coordinates used to slice the alignment
    align_records = make_records(start, end, block_id)
    # in the alignment, s2 is in reverse complement relative to its genome
    # In order to be sure what "genome" coordinates are for s2, we first slice
    # the alignment
    aln = aln[start:end]
    # then get the ungapped sequence
    s2 = aln.get_seq("s2")
    # and reverse complement it ...
    selected = s2.rc()
    # so we can get the genome coordinates for this segment on the s2 genome
    start = s2_genome.find(str(selected))
    end = start + len(selected)
    for record in align_records:
        if record.seqid == "s2":
            record.start = start
            record.stop = end
            record.strand = "-"
            break
    return align_records


@pytest.mark.parametrize(
    "start_end",
    (
        (None, None),
        (None, 11),
        (3, None),
        (3, 13),
    ),
)
@pytest.mark.parametrize(
    "species_coord",
    (
        ("human", "s1"),
        ("dog", "s3"),
    ),
)
def test_select_alignment_plus_strand(species_coord, start_end, namer):
    species, seqid = species_coord
    start, end = start_end
    aln = small_seqs()
    # the sample alignment db has an alignment block that
    # starts at 1 and ends at 12. The following slice is to
    # get the expected answer
    expect = aln[max(1, start or 1) : min(end or 12, 12)]
    # one sequence is stored in reverse complement
    genomes, align_db = make_sample()
    got = list(
        get_alignment(
            align_db=align_db,
            genomes=genomes,
            ref_species=species,
            seqid=seqid,
            ref_start=start,
            ref_end=end,
            namer=namer,
        )
    )
    assert len(got) == 1
    assert got[0].to_dict() == expect.to_dict()


@pytest.mark.parametrize(
    "start_end",
    (
        (None, None),
        (None, 5),
        (2, None),
        (2, 7),
    ),
)
def test_select_alignment_minus_strand(start_end, namer):
    species, seqid = "mouse", "s2"
    start, end = start_end
    aln = small_seqs()
    ft = aln.add_feature(
        biotype="custom",
        name="selected",
        seqid="s2",
        on_alignment=False,
        spans=[(max(1, start or 0), min(end or 12, 12))],
    )
    expect = aln[ft.map.start : min(ft.map.end, 12)]

    # mouse sequence is on minus strand, so need to adjust
    # coordinates for query
    s2 = aln.get_seq("s2")
    s2_ft = list(s2.get_features(name="selected"))[0]
    if not any([start is None, end is None]):
        start = len(s2) - s2_ft.map.end
        end = len(s2) - s2_ft.map.start
    elif start == None != end:  # noqa E711
        start = len(s2) - s2_ft.map.end
        end = None
    elif start != None == end:  # noqa E711
        end = len(s2) - s2_ft.map.start
        start = None

    # mouse sequence is on minus strand, so need to adjust
    # coordinates for query

    genomes, align_db = make_sample(two_aligns=False)
    got = list(
        get_alignment(
            align_db=align_db,
            genomes=genomes,
            ref_species=species,
            seqid=seqid,
            ref_start=start,
            ref_end=end,
            namer=namer,
        )
    )
    assert len(got) == 1
    assert got[0].to_dict() == expect.to_dict()


@pytest.mark.parametrize(
    "coord",
    (
        ("human", "s1", None, 11),  # finish within
        ("human", "s1", 3, None),  # start within
        ("human", "s1", 3, 9),  # within
        ("human", "s1", 3, 13),  # extends past
    ),
)
def test_get_alignment_features(coord):
    kwargs = dict(zip(("ref_species", "seqid", "ref_start", "ref_end"), coord))
    genomes, align_db = make_sample(two_aligns=False)
    got = list(get_alignment(align_db=align_db, genomes=genomes, **kwargs))[0]
    assert len(got.annotation_db) == 1


@pytest.mark.parametrize(
    "coord",
    (
        ("human", "s1", None, 11),  # finish within
        ("human", "s1", 3, None),  # start within
        ("human", "s1", 3, 9),  # within
        ("human", "s1", 3, 13),  # extends past
    ),
)
def test_get_alignment_masked_features(coord):
    kwargs = dict(zip(("ref_species", "seqid", "ref_start", "ref_end"), coord))
    kwargs["mask_features"] = ["gene"]
    genomes, align_db = make_sample(two_aligns=False)
    got = list(get_alignment(align_db=align_db, genomes=genomes, **kwargs))[0]
    assert len(got.annotation_db) == 1


@pytest.mark.parametrize(
    "coord",
    (
        ("human", "s1", None, 11),  # finish within
        ("human", "s1", 3, None),  # start within
        ("human", "s1", 3, 9),  # within
        ("human", "s1", 3, 13),  # extends past
    ),
)
def test_align_db_get_records(coord):
    kwargs = dict(zip(("species", "seqid", "start", "stop"), coord))
    # records are, we should get a single hit from each query
    # [('blah', 0, 'human', 's1', 1, 12, '+', array([], dtype=int32)),
    _, align_db = make_sample(two_aligns=True)
    got = list(align_db.get_records_matching(**kwargs))
    assert len(got) == 1


@pytest.mark.parametrize(
    "coord",
    (
        ("human", "s1"),
        ("mouse", "s2"),
        ("dog", "s3"),
    ),
)
def test_align_db_get_records_required_only(coord):
    kwargs = dict(zip(("species", "seqid"), coord))
    # two hits for each species
    _, align_db = make_sample(two_aligns=True)
    got = list(align_db.get_records_matching(**kwargs))
    assert len(got) == 2


@pytest.mark.parametrize(
    "coord",
    (
        ("human", "s2"),
        ("mouse", "xx"),
        ("blah", "s3"),
    ),
)
def test_align_db_get_records_no_matches(coord):
    kwargs = dict(zip(("species", "seqid"), coord))
    # no hits at all
    _, align_db = make_sample()
    got = list(align_db.get_records_matching(**kwargs))
    assert not len(got)


def test_get_species():
    _, align_db = make_sample()
    assert set(align_db.get_species_names()) == {"dog", "human", "mouse"}


def test_write_alignments(tmp_path):
    genomes, align_db = make_sample(two_aligns=True)
    write_alignments(
        align_db=align_db,
        genomes=genomes,
        outdir=tmp_path,
        limit=None,
        mask_features=None,
        stableids=["not-on-s2"],
        ref_species="human",
        show_progress=False,
    )
    aln_path = list(tmp_path.glob("*"))[0]
    aln = load_aligned_seqs(aln_path, moltype="dna")
    assert len(aln) == 3
