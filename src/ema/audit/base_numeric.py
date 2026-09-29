"""Reviewed fixed text retained from the AUDIT-01 audit base.

Each digest approves one exact paragraph or cell; edits require a new review.
The grouped reasons are legislation, law or ISO standards, section numbering, the firm's
cover, her fixed chapter prose, heading slot values she writes the same in every audit and
her numbering's picture bullets.
"""

from __future__ import annotations

import hashlib
import re

_NUMBER = re.compile(r"\d")

# SHA-256 of stripped source text (of the bytes, for a picture; of the line with each field as
# `{PAGE}`, for her page numbering), grouped by review reason.
_ALLOWED: dict[str, frozenset[str]] = {
    "law": frozenset(
        {
            "d9a04b46613d4819607496232c755c56c8687fcb68b97b6dd6b50f8bfbb122c2",
        }
    ),
    "law_or_standard": frozenset(
        {
            "dc339c5c011ce8dcc80ad54d6deae660564c89995d1bb692eb42e3ea6be22be7",
            "1b5a62e011f81f6dd0a3d82beb827198d617951b98b0cff7379beb7cf25e1e07",
            "190c5cb90c21261d808d3ed67ba968af1b1572d5df6a13ec521bdb5dec33148b",
            "e2c6f7c57c5eb44385ed384e5e49a3f6412f8077912515ac304304e2c0806a61",
            "9bcf2f9fd12e5c552c3a4cbaa5c5286e3ab2fa5c237f33b828b472f9169d5dd7",
            "150fd55e1e9b59eaa90eb33761467db12aeea1713769b2b612af55618c2d2381",
            "8284dd90f04ffd2466d9bbe1021dd5db103f99533167953703e32117d1b52a2c",
        }
    ),
    "legislation": frozenset(
        {
            "62206578454bd09214bc8446b198a8144a99f6a6485536b9a717912c6250ab07",
            "6652b4f3ba8162e81558a6d6f551de1d7cc26b3e9f46cbc20675caded81e2cde",
            "cc340442fc7400673242e4bb290c886a77c8f89450d083ca9fa2db696eae28a8",
            "55aa9d42116a6f3a4e194f47472ea56d3003d172887ba4f606797c6c13d69d99",
            "85efb8cf348be5b2a6a46226b6df4e8de7a3df3bfe86126bf4ca39ef4c9b4227",
            "9429bb07865dd0f77c5cd9971638006980ef5fa1883967c311bfa03c16c800a2",
            "40ece925bc8d97bcb883d1592dcd9265705f3e22b8cfd5959eb334faf74e75f0",
            "fc74bbd5027b8f7646e3fd2ebbe047611669bf9106dbbe5f24a229a9c832f727",
            "d202e6c8f9710a876dffee6b783f1ee539c6daf16c858830fc71bd7e068d472c",
            "889a833ec1e91d9d09bcfc2157755733d9ba0baaeae645bbc2c9e7d63a5ea8de",
            "0f829e333f5f2ea4ec054f5e0bee8a5279e5bd36dd26b2e6ec18e466085e5d7a",
            "9f4c40c1d911d8c797bb74f423047ba01acff3f1f639be1ec7844a7e4170f12e",
            "d309296dc2882df826dc5fee7d17ad5ca723ab830d8e599b770aef80b4f33968",
            "8800b2cd864675ce07d2b07c2d3c40381d8b69e2bd6b281fc2d4a0c1f6fcfc56",
            "1d875018f4722fe3ca5aab5d5c9abe8ad08d527ffd1447f919f3ff18fe15692e",
            "f3bf81e21717e2b392439dd26732fe0b4b8484140d756f4f8e5d3af565cd2263",
            "0e445da5463648735c1d95f068925ed9a557b8975915af93026142cc3e0bd4f0",
            "11cabb6b53795bab94f7c30c32bb5575568e149db8fcc854f29ee25e310157d2",
            "23474e568201ce1c025bada9bd806a425c6044dcfa2c070836607f205204b725",
            "683024f7b01fb6399d10b921c137b2630659f63469b11871a6bf085cbd867a2c",
            "5b1650566b9b2d4ab9160c9640f822e91321643a2f87b6e1119c7029e96efa97",
            "6b4929025cdd211597840ff31540d791a7f9d2216db3f84d881506038a69a660",
            "56c4cb6452d2ca00fea5a831b8890c205a607e2e8cadf7a925e7e53c69368625",
            "d263971a1b23814c5a5b541ddb6a2c5341b6af7e972088e67673308c1d519fc0",
            "3a0ca2e268e9955684e27bf77343800274effe9e741e1e1e5660cef1f9e56080",
            "95256f4d1397ca341652cde4ea57b97d4e736b43457a89ff7216d95da70e46c3",
            "c4c446c0e263d14d13bed02ffffaeaadc44b2018767a6a14dc824cfce43be191",
            "1c0919089b62a41e72f81116b3dfcb26256b878b53c560df7fb81ca6a8114053",
            "4b109d4541cfaafb8f62d5d941d12ddaef2f0e92cfdc7110385e4d487e9201ca",
            "4931a663a71c33617aedfa7fe33e40d739ee57e650561c8a04b9fa42886adcaa",
            "eb67d260f285afb49c82cf711b2f69beace30f81a10684f4db8e9e633c8962da",
            "934d5512052f7522ca90854f6c84805901d239f9338aff7bb9df31ab57d91482",
            "2b559eb5537281c218b20c7bc88602daf42d9a3acc88c55c6bfa6b54b58f533f",
            "3c746b45324fd0a2b1bdf1a5184460fd8699ecbd00e10550248c6ce659c56309",
            "0ef544c5c8bd6b87f26bfec0088f5aff04fd06b0526b8e9db69a76df5e6837dc",
            "a46ff594683464c36cff1949c1eed319a52ca73d0549af7183cc6add3340778f",
            "54d9d4328eadef60bff4e5e0a03ed8b23afe8846626caf4199a8330028bbe110",
            "c168c4e9183b3ce7dd02832acf67a37dcbec8cf08568fff945cbff908c05eecb",
            "ba20fbf64472ba848a9b9bf5aaa471c9d6819cea31f5366253e46aa79b3b300e",
            "c3e01c2d7d83677ae87702d9967d24ade4704d6e74bb8b71f36af5513d9ecd9e",
            "f10cb2a1ea6d3986b1da2bef610f578de973cb3bb36d9e17e1a8c01d84dc74e5",
            "a5e3df2ab98b1c191b9e1754527ba3532d14137f3e0fc801ff5374c363c75a1c",
            "0219b9b498afbe3a5a5be222544d6d4ee09ff804d6452aec28e0788e6e70077d",
            "eb331ffe280a152c3be383c7f60347f6fb4cba7adfef2520ef518617b9add78d",
            "d9a2e0a069f3962e5e6c8a98c84a2806ea6a3ee981dacf50f11abb2221c5ae33",
            "713c49f994ce2b995a1afb54096342fcc0105759353ffb7f7d61f7e32d26c4a9",
            "5a2e748bdad3c01d4bc975b876675d83c3ccb464f24b18e7abd3a93c381b2795",
            "758ff3eec363a43e740d0def417b007783eb5f137074ed96fed916b3d23a310a",
            "f06d0aaee4c27d3733a5e0af15c094fb73f692b7cdeaa72b2504baec54a24129",
            "3995bcabaff9585597182159802287f54d57df45cf564dff77f5f1467c76640d",
            "4ca4b45954a4b6d7fa6daad21f3e8fbb807e51736dc1d17dd37a6cc96f4c363e",
            "2dba3e9bb22e3f508cb3d35e3ad9636b5c1cdfcd68fd6493c2c300aeb9fd1c03",
            "d97e062ea9b9caf86c7c00343da37569bd88b44022c1dfcc17190987071795e2",
            "cb28d10abbbe01f3b27aa1323fb70463cc6779a3eecb697ce65d8d9c9903665d",
            "bec596733436ba4c5ed9116077818eb242cfbaf0f475972f3cbf68f8f00174d2",
            "d40234f0b125352e4aaee0c761ce5658ad324b823969a38fd15ad4c2b7bb89d5",
            "b7abdb4076453ec56f61c3913699a69de69e01598421b3e80bf63c9d20629e4e",
            "5f5c0cde94636d88a159e7dc00fa09a0ae68b687d4577e6b0ed9c8a6e065d005",
            "0f52ecc6a768fa6b9e121908febd3e315c44e9d6ca1aa23de9f3343b35fe9bdb",
            "30975502c640e2b5632aa81b76026dd7d9e3cbe3b7e9d8f89a6150780d20d450",
            "f91ee614c715d6a26b21be12ecac91d339d8a70b2dbdb2b73fac0930c6510ff1",
            "e7a96af713d92f97ec53e4edad9d1c12ff4b4d51f2be2db031150b3de56003c3",
            "0aa371f08723781240c5b11176a8a776d855eb0bfb9562b315d8e01bed6a7bbc",
            "842f82105291c557971ae7da2d416b201cc1e195241e50829e97f12a66dcfaad",
            "df60cb2b87281922f63c540e7b2b7cbc2fcb209845afa62c7b5be0f7650f3794",
            "705951459f4fd43831f49e491518f9288329d4a11986d457dd652feb3c4bd638",
            "4fa4e03768d75f1c0be1b3ae33e0ad54b09a467fb1f1ac7bebadc33815cbe3d3",
            "9f9bea4c713539a84e3c5f0b0e977bb36d0c5acde9771b592aeefbba0f03ca8c",
            "388b8f4aae7e7494dae81d0f276809e7180db6ef1fdee5f53ace7e2a44319157",
            "6a658478868d0219ffb41b8f1fe4f787f41278d50c5f643ca3ec53d4e50b551a",
            "5199c4cbeb2aeca4e61a00892178baf5fb3c8d4bd52ca63a4ca595eae2da37d0",
            "2a9f2e72e78caf5a72f21177b9cd6285bb704cb2671aa8a1caf142be8f2ae17b",
            "18fa358ed86ed037ab62095361319628a6fb9f8bbdb5c29d460d2f1b2ed37c51",
            "180f629e150016cf33a5f41e2f361766366f88a1aeeacd5c6d92fd4a87421091",
            "2fe31601a524e5b7169501af3806493aea952d029facc4c59f248e88fcfd6cd6",
            "bee84e88285cd460fd9bb13061b655df35387958a480ef96e77ccfb49f9b0b42",
            "f9d2172c0a721e131fce0bd85b0c468b8ecadcdd6bace54c3ea11fa7b2105ea1",
            "f900e3ac79d296984c22c847a6df7615e50ef7c6bb1308202fc3c0977d872de3",
            "6e74fadffb2ab401b21cdaa7b61cfac62fa76592524dfca69269c81993bdb05f",
            "a81d1ce1176b86c8efb012f53f52ead7a7339e4123731dbeec85d9c3c63e0ff9",
            "7334fe4a0b689a6b29c78c39b33724a409411316657a729dc4e7f98e166cf851",
            "896b65c2fb1ee4aaf416f67d5a0f486b2f26b7efed6fae250b7ac1c2a5aab5d5",
            "f2bf1aee8ad9554cd6a3b2772606b33d19e632b7ddce049cdcbbe8492e52724b",
            "e53a0b0209a9d55770dc13b8d4a4496e688133c4d93ac227407e1b986ffdfa17",
            "a721fc95bed8788b27afee69fa545a133263acbb1554ff411a7c6e35eb3c88ad",
            "a899be2b8507ace15c5472ab362e11b766a90db6440a11bf08d3269c95ef51be",
            "f06b4d46bd7639e36872551f49d06d35b7a20830aaa0a8ae82a3d55ed8fb0b1e",
            "e6f32483ce1833dfad213fe92dc8fd5f3f1e0bbb68bb06322a4e4de41924ab3d",
            "1471464e40db90669baf5de27ac5b44475fd6bab377cc1cdd269d37c1c90add8",
            "903784ce72cf828aed70029a5545fb4b4fce17fe60015c20b8807131e4b973f2",
            "168c8e66c13f581ca6914467941bce62bda64e210978805ec32e60c608664dda",
            "9522eefa70eb703a9ee755e8daf5e4765b84de081c22e4594b7b82a54b03af60",
            "0bd3dba2af3f4fde18a1918fa80a3a71851f5162980a20c334287963c35885bc",
            "fc5dabd487792526cdfb40450a7d2c75ca4819268d32c9840de21969553ba344",
            "06c1b8bdffe102c92dee70fae08b020189416166f78488b83b50c93d16c191b8",
            "0e9cacfd3f2139d5cf0aadb6cd2321d23a811601351e28942cfdc778ed28f274",
            "bfd3ba32a185e6c65022174b171fd23a529787216a47eecff248fdd08ccb7033",
            "af0451ffba4f14de159a7d81fe50f50923a0bcad2ffa58b43e1c6de9134d3033",
            "000fbab3617a1af874dc55a4aa902b209ca68abbe27ea0de88cae830f1b5e1c1",
            "e15ab7e4091594d0caca63455188ec3b64ef3fd18769c20363070e5e784414e5",
            "10dfc5603e8b6a8c1990bab6d6c2b4fbf1f0117eec776debcb059c827ee6ef71",
            "c138e0369478433167172a2f11dce462eb851b289d8808c89fe8e8c2a022a120",
            "47a5d81f4f3dc20b17d8fb4555cece7f06bed255253b2fc2e953386528e74f84",
            "0d0d80ece64914eb875f1ab1e12f2514dbdf29646bdc3a997e594fb345585cf7",
            "51f424657cbca149dc3ea3da6128e01fb608f2b9a3e0eeb35f41cfe79a3bb8fd",
            "c5de2be9eebec268e26be52af29d253f7b3f585876cd3940cd9273ba5889ec10",
            "850700ce1716dcb44aa1766a73e6a6a5f5ba9c23428332b29e67e19ebe74a950",
            "d5d08737c333f205feae1d0512d601c33e53be7a3514e943134db54f7e19b451",
            "760bc10aef0bf3dee2bdb46f3d4f91971017e8eb5273c54100b2e4de127f9717",
            "c452cce16dca0c16603e4d9f0e6e3de4a6bebf9ea8f37f585e90ea357da52bb4",
            "507673fd6470567fb01141d19e816919fcdcacd6c76cdbfa3de7b51a2ad6a414",
            "f4edc502c6c7e5e63f8c4441361c2cdeaef79d8bddcd931171fcdeb878af25d8",
            "e4c2a40fe4155ce1b9233ffa80f18883a8c4b23c77b29c1613257cc53d26d3ea",
            "3424629337964a5c9827ffe0a735bf33efbb9239fb8fdf6040a94681c75e6eca",
            "2f9c1f35da2164f1441aac647b53ae0fa8ae22b511d99b126937dbdde15e0c2e",
            "bf201b1069e31b515a3f785929e9c76da8317b10d6c1307d0aa10123455f4350",
            "efdb1252e8be58afe38222f6997ac6e15c9a459f276a8f641d10f1e998b5761a",
            "941dbcc2af492066f2af8c22ac89cf5ec87b985ffb6b9e7f3c355e549b8c4977",
            "30467ed1fe0c62caf19115add1e06901b2c1fbb99c63738079f4f60df9838f9f",
            "329f8d7be4737123eb81d0a73fa46aff6417d95b2a44d9dd00917ae15472f102",
            "bbce676d7c43fc41cc582bf3af40d2c720fe3ee6284f32768c1d8c0c93f61549",
            "41dd73da080897855f2ece28a348a2c873bd5045c7105287fd85e8e8d86ba95e",
            "92cb8d7775440e0eb3d45db7179ebb9c325856b21a54441b9fc226f59263326b",
            "b682da737494f745b00d7ff581a79af4518f979d8878ceda3aa0eb2e3de9900d",
            "8872faa6c3a30a478c4d8b3b62f0fae84c9f61f17c4e950d6852926051b83884",
            "ae51aa7f3e0100dfaad92e46f2b973d7cd8e660ceeda2ff0b555861ead72dc39",
            "eb5404dc72b6e4d9c1b97e39d78604ecfffdac0105315800a993b43df1e34939",
            "433ba0f30e8404239bb0ef03c557f05e85ba80ac9f192719e49efbb396502fc2",
            "be6ee311c232a1c345194ba77c5329b412a9f499d8bc427965f04fbadfdbbf3d",
        }
    ),
    "cover": frozenset(
        {
            "dbc761c895174f70e9d1f7a0f2c082737ed8777fcc82c4607a02b6ca1bbe7a3a",
            "a586586f40c69056df477af8f2b3d2fb056ff217e8f44bf3dada80d524f06ac8",
            "b9e5cbf7dcce12bbc67d27c081155d678d5316e03ae955e3af3dc3929ac2789e",
            "ddd1c5629bd6d7705a973ced917ec2cf868420819d204f99ef9ae6d9e5784057",
            "7eeae81ab3e1a53621a7c963a0325a16f7ee4d459e3523da124557406e5a9625",
            "615140c5115b4e3b1ca4322776c03aa2270ba51bf656483de1828fbff35a1eca",
            "10c443b3f08afdc1f8b79a43c9f0f41c0c020bcbdde4bec54a9e9e6578bc1413",
            "d355ca30caf67267ede78574966d9d14ffce15147699d59e5e058d2237ace6dc",
            "5e5c53373b4f2c368af8787c2762e9a60c890b94eec491e6260abede28c04e0c",
            "8ee6d423ddfc242abd6b5e544614e762ec05d85fa8e646886dccf29846638c00",
            "dc339c5c011ce8dcc80ad54d6deae660564c89995d1bb692eb42e3ea6be22be7",
            "ce2101a243626de50c565e2cd1dce8356ebda9fe6349540118367f9e4213b4ab",
            "316ff31d3d865012e68e8a6d8e6316c30774e2a8b164b4b29042594ab7ddbfa1",
            "657a2e116824008a23ee43a4f144e1846862a4aec7b61a060638a1cea00dc48f",
            "e1998bac3bb79eb4a3f286abe58ba8d2b69e93ecb013adaf274ccd26bea619fc",
            "1b5a62e011f81f6dd0a3d82beb827198d617951b98b0cff7379beb7cf25e1e07",
            "a3d233c4ac80e536148d04ac3f7668bf8c55858d50a7a57f9d7838afba94f7cc",
            "5e8b346d2d35cecb008ab746f26f450f5b977c4dd8414f1d609d2b93c016447e",
        }
    ),
    "fixed_prose": frozenset(
        {
            "5f74504eea38468ba4b6f8aad3fe9b11ddf875fcc164056334683372fd047007",
            "b0e90f430d028ece97ebeb4f6ec616fb46a41b29765d2dab7dcd9e2d617506b7",
            "a2fa2a25933fba45a62f19d65f4004a012052f6ae1c979da879ce03b9c7f904b",
            "d8d7ebb4ff43d96f96f43d860318753cd2ddbde63310279612ad3f7f2cb500fb",
            "464ee8e7dda8a491e2ceeb22167cac6dc2c5c8426ce436850acc2ae613d4e192",
            "6a1c7ab012ca5b8f224287338d54c7b78c85b0296a34722b343b9e8844aa503c",
            "262fea5469ef926dd5d6a57bd04dfdf951f1862fa7c1404922748e3329f98d79",
            "1f6efd90be11edc6a65bc27bc6b19ce898252a9a593518bc169e2e0e1a7f2704",
            "f2e4acb6aaec67dd705dba01d1e354a5620aae2b7346d752702db838b383148d",
            "1c2213dd8172f369ecccdb585b93bf454fc8146d1563533fa8839a2fbd2f0fe3",
            "6b8ef391209eb4ab90d89a20468760e7240ffe3f60b6d81045e35befa71d47f1",
            "9f88e0b4945e0f79a5df7f67fb64bc1857b9c1159debc358462fcc3a8cf507d5",
            "0801d83eddd131f555bb25e045558af99f323ab3abba257081a8c761c63c106a",
            "9cdf7c2763a4eb0e954ef4fb39457be427035ed3a3715310ac740e3e6031776c",
            "1066f2714e873d9724593909b04490aa013ce12d797dcf09c576cb993aafd805",
        }
    ),
    "heading_slot": frozenset(
        {
            "9f16ac97114f27baffcbe3d2b4d8a0aa937c1dded984ab51102bfe023c077834",
        }
    ),
    # Her numbering's picture bullets (word/numbering.xml), in every audit she delivered.
    "picture_bullet": frozenset(
        {
            "ebe0f3b27259f742c5e959c6776d24e852f4e5b5387018c0950c42d24562f9dd",
            "039fe79b74e6d3d561e32d4af570e6ca70db6bb3718395be2bf278b9e601279a",
        }
    ),
    "section_number": frozenset(
        {
            "baae87d18c4c4f54293476228d8ac4e868447cc1f9da23620cde1a2248ce59e5",
            "ff083f2fb4a9bb5d035a3871bf7a9d2ee2c304fa71c7013f8001414c4cacc0f9",
            "63a250985c2dda7f0d414ee03eb7a2b6f38fa98ec0d122a335ee09b5b6740fe7",
            "11cc8ddc90dc52c441cd2356be50ceb73186445a710e06b3b5f402c3a7ea0c2b",
            "7ea2806f652962f25200da029fb57b711f294f331307c37dd0f076253b9173da",
            "d64f18a0b9f98477f84ade92f5b6ab7d941d30478489f8083784f3108f3112a3",
            "5211b53c427f10c43a1b36c5ba3f84cb9d32c597c1822752ad79a01ba91df8ec",
            "eae1bdcef10f21c545719ef7fe428384202e7fe2a893586c74a33dda10b141f5",
        }
    ),
}


def has_number(text: str) -> bool:
    return bool(_NUMBER.search(text))


def approved_fixed_text(text: str) -> bool:
    digest = hashlib.sha256(text.strip().encode()).hexdigest()
    return any(digest in entries for entries in _ALLOWED.values())


def approved_fixed_image(data: bytes) -> bool:
    digest = hashlib.sha256(data).hexdigest()
    return any(digest in entries for entries in _ALLOWED.values())
