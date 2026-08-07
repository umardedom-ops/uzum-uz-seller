"""Audit yadrosi — pul topishning 5 ta yo'li (SPEC 5.1–5.5).

Bu modul mahsulotning yuragi. Shuning uchun:

  * Barcha funksiyalar **sof** — bazaga ham, tarmoqqa ham murojaat qilmaydi.
    Kirish ma'lumoti dataclass, chiqishi `Finding`. Shu sabab Uzumga
    ulanmasdan to'liq sinash mumkin.
  * Pul **Decimal** bilan hisoblanadi. Float bilan hisoblangan zarar
    da'voda tortishuv keltirib chiqaradi.
  * Natija "aniq fakt" emas, "tekshirish kerak" (SPEC 9.5). Kichik farqlar
    `WATCHING` statusi bilan belgilanadi — sellerni noto'g'ri da'vo bilan
    Uzum oldida noqulay ahvolga solmaymiz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.db.models import DiscrepancyKind, DiscrepancyStatus

# --- Shovqinni kamaytirish chegaralari (SPEC 5.1, 5.3, 5.4) -------------- #

# 1 dona farq — o'lchov xatosi bo'lishi mumkin, kuzatuvga olamiz.
# 2 va undan ortiq — da'vo qilamiz.
CLAIM_MIN_QTY = 2

# Komissiya farqi shundan kam bo'lsa — yaxlitlash xatosi, e'tibor bermaymiz.
COMMISSION_MIN_DIFF = Decimal("1000")

# Logistika farqi shu foizdan oshsa — tekshirish kerak.
LOGISTICS_TOLERANCE_PCT = Decimal("15")

# Qaytarish shu kundan ko'p vaqt omborga tushmasa — yo'qolgan hisoblanadi.
RETURN_GRACE_DAYS = 14

_CENTS = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    """Pulni 2 xonagacha yaxlitlaydi (bank yaxlitlashi emas, odatiy)."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Finding:
    """Aniqlangan farq — `discrepancies` jadvaliga yoziladi."""

    kind: DiscrepancyKind
    sku: str
    qty: int
    amount: Decimal
    status: DiscrepancyStatus
    details: str

    @property
    def is_claimable(self) -> bool:
        """Da'vo qilish mumkinmi (kuzatuvdagilar hisobga olinmaydi)."""
        return self.status == DiscrepancyStatus.NEW


# ======================================================================== #
# 5.1 — Yo'qolgan tovar
# ======================================================================== #


@dataclass(frozen=True, slots=True)
class StockPeriod:
    """Bitta SKU uchun [T1, T2] davri bo'yicha ombor harakati."""

    sku: str
    period_from: date
    period_to: date
    qty_at_start: int      # qoldiq(T1)
    qty_at_end: int        # haqiqiy qoldiq(T2)
    received: int = 0      # omborga qabul
    returned: int = 0      # qaytib tushgan
    sold: int = 0          # sotilgan
    written_off: int = 0   # hisobdan chiqarilgan
    unit_cost: Decimal = Decimal("0")  # tannarx yoki sotuv narxi
    # Inventarizatsiya kunlari — bu davrda qoldiq qayta sanaladi, farq
    # tabiiy bo'ladi va da'vo qilinmaydi (SPEC 5.1 shovqin kamaytirish).
    inventory_days: frozenset[date] = field(default_factory=frozenset)

    @property
    def expected_qty(self) -> int:
        return (
            self.qty_at_start
            + self.received
            + self.returned
            - self.sold
            - self.written_off
        )

    @property
    def diff(self) -> int:
        """Musbat bo'lsa — tovar yetishmayapti."""
        return self.expected_qty - self.qty_at_end

    @property
    def has_inventory(self) -> bool:
        return any(
            self.period_from <= d <= self.period_to for d in self.inventory_days
        )


def audit_lost_stock(period: StockPeriod) -> Finding | None:
    """5.1 — kutilgan va haqiqiy qoldiq farqi.

    Qaytaradi:
      * `None` — farq yo'q, manfiy (ortiqcha tovar — bu bizning muammo
        emas), yoki davrda inventarizatsiya bo'lgan
      * `WATCHING` — 1 dona farq, kuzatuvda
      * `NEW` — 2+ dona, da'vo qilish mumkin
    """
    if period.has_inventory:
        return None

    diff = period.diff
    if diff <= 0:
        # 0 — hammasi joyida. Manfiy — omborda ortiqcha, seller foydasiga.
        return None

    status = (
        DiscrepancyStatus.NEW if diff >= CLAIM_MIN_QTY else DiscrepancyStatus.WATCHING
    )
    amount = _money(Decimal(diff) * period.unit_cost)

    details = (
        f"Kutilgan qoldiq: {period.expected_qty} dona "
        f"({period.qty_at_start} boshlang'ich + {period.received} qabul "
        f"+ {period.returned} qaytgan − {period.sold} sotilgan "
        f"− {period.written_off} chiqarilgan). "
        f"Haqiqiy qoldiq: {period.qty_at_end} dona. "
        f"Farq: {diff} dona."
    )

    return Finding(
        kind=DiscrepancyKind.LOST_STOCK,
        sku=period.sku,
        qty=diff,
        amount=amount,
        status=status,
        details=details,
    )


# ======================================================================== #
# 5.1-bis — To'plangan yo'qotish (butun faoliyat davri)
# ======================================================================== #


@dataclass(frozen=True, slots=True)
class CumulativeStock:
    """Do'kon ochilganidan buyon bitta SKU bo'yicha barcha harakat.

    Qoldiq TARIXI shart emas: do'kon boshida qoldiq nol edi, shuning uchun
    barcha harakatlar yig'indisi bugungi kutilgan qoldiqni beradi. Uni
    bugungi haqiqiy qoldiq bilan solishtiramiz.

    Shu sabab bot ulangan kuniyoq butun faoliyat davri bo'yicha
    yo'qotishni ko'rsata oladi.
    """

    sku: str
    qty_now: int             # bugungi haqiqiy qoldiq
    total_received: int = 0  # barcha yuk xatlari bo'yicha qabul
    total_returned: int = 0  # omborga qaytib tushganlar
    total_sold: int = 0      # barcha sotuvlar
    total_written_off: int = 0
    unit_cost: Decimal = Decimal("0")
    # Tarix to'liqmi: sotuv tarixi qabul tarixidan oldin boshlanganmi.
    # Noto'liq bo'lsa hisob SOXTA yo'qotish ko'rsatadi (SPEC 9.5).
    history_complete: bool = True
    first_movement: date | None = None

    @property
    def expected_qty(self) -> int:
        return (
            self.total_received
            + self.total_returned
            - self.total_sold
            - self.total_written_off
        )

    @property
    def diff(self) -> int:
        return self.expected_qty - self.qty_now

    @property
    def data_is_plausible(self) -> bool:
        """Manba ma'lumoti ishonchli ko'rinadimi.

        ⚠️ 2026-08-07 da haqiqiy do'konda aniqlandi: Uzum ba'zi
        mahsulotlar uchun "qabul qilingan" miqdorni **0** qaytaradi,
        holbuki tovar sotilgan va omborda turibdi. Bunday holatda
        formula "yo'qolgan tovar" deb ko'rsatadi — bu **yolg'on**.

        Qoida: qabul nol bo'lsa-yu, sotuv yoki qoldiq bo'lsa — ma'lumot
        to'liq emas, hisoblamaymiz (SPEC 9.5).
        """
        # Qaytarish sotuvdan ko'p bo'la olmaydi — sotilmagan tovar
        # qaytmaydi. Bunday raqam manba maydoni biz o'ylagan narsani
        # anglatmasligini bildiradi (2026-08-07 da haqiqiy do'konda
        # ko'rilgan: 9 sotilgan, 23 "qaytgan").
        if self.total_returned > self.total_sold:
            return False

        # Chiqim kirimdan oshmasligi kerak: sotilgan + qolgan + chiqarilgan
        # jami qabuldan ko'p bo'lsa, qabul ma'lumoti to'liq emas.
        outflow = self.total_sold + self.total_written_off + self.qty_now
        inflow = self.total_received + self.total_returned
        if outflow > inflow:
            return False

        if self.total_received > 0:
            return True
        # Qabul yo'q, lekin harakat bor — manba ma'lumoti to'liq emas
        return self.total_sold == 0 and self.qty_now == 0 and self.total_returned == 0


def audit_cumulative_loss(stock: CumulativeStock) -> Finding | None:
    """5.1-bis — butun faoliyat davri bo'yicha to'plangan yetishmovchilik.

    ⚠️ Tarix to'liq bo'lmasa hisoblamaymiz. Sabab: agar sotuvlar tarixi
    qisqa bo'lsa (masalan API 1 yil bergan, do'kon 2 yildan beri ishlayapti),
    "sotilgan" kam chiqadi, kutilgan qoldiq oshib ketadi va bot mavjud
    bo'lmagan yo'qotishni ko'rsatadi. Sellerni bunday da'vo bilan Uzum
    oldiga yubormaymiz.
    """
    if not stock.history_complete or not stock.data_is_plausible:
        return None

    diff = stock.diff
    if diff < CLAIM_MIN_QTY:
        # To'plangan hisobda 1 dona farq shovqin — kuzatuvga ham olmaymiz
        return None

    period_note = (
        f" ({stock.first_movement:%d.%m.%Y} dan buyon)" if stock.first_movement else ""
    )

    return Finding(
        kind=DiscrepancyKind.LOST_STOCK,
        sku=stock.sku,
        qty=diff,
        amount=_money(Decimal(diff) * stock.unit_cost),
        status=DiscrepancyStatus.NEW,
        details=(
            f"Butun faoliyat davri bo'yicha{period_note}: "
            f"omborga {stock.total_received} dona qabul qilingan, "
            f"{stock.total_returned} dona qaytib tushgan, "
            f"{stock.total_sold} dona sotilgan, "
            f"{stock.total_written_off} dona hisobdan chiqarilgan. "
            f"Kutilgan qoldiq: {stock.expected_qty} dona. "
            f"Haqiqiy qoldiq: {stock.qty_now} dona. "
            f"Yetishmayapti: {diff} dona."
        ),
    )


# ======================================================================== #
# 5.2 — Yo'qolgan qaytarish
# ======================================================================== #


@dataclass(frozen=True, slots=True)
class ReturnRecord:
    """Mijoz qaytargan tovar."""

    sku: str
    return_id: str
    qty: int
    returned_at: date            # mijoz qaytargan sana
    received_at: date | None     # omborga tushgan sana (None — tushmagan)
    unit_cost: Decimal = Decimal("0")
    is_returned_status: bool = True  # Uzumdagi status "qaytarildi" mi


def audit_lost_return(item: ReturnRecord, today: date) -> Finding | None:
    """5.2 — qaytdi, lekin omborga tushmadi.

    Uch shart birga bajarilishi kerak: status "qaytarildi", omborga qabul
    yozuvi yo'q, va qaytarilgandan {RETURN_GRACE_DAYS}+ kun o'tgan.
    """
    if not item.is_returned_status or item.received_at is not None:
        return None

    days_passed = (today - item.returned_at).days
    if days_passed < RETURN_GRACE_DAYS:
        return None  # hali yo'lda bo'lishi mumkin

    status = (
        DiscrepancyStatus.NEW
        if item.qty >= CLAIM_MIN_QTY
        else DiscrepancyStatus.WATCHING
    )

    return Finding(
        kind=DiscrepancyKind.LOST_RETURN,
        sku=item.sku,
        qty=item.qty,
        amount=_money(Decimal(item.qty) * item.unit_cost),
        status=status,
        details=(
            f"Qaytarish №{item.return_id}: {item.returned_at} da qaytarilgan, "
            f"{days_passed} kun o'tdi, omborga qabul qilinmagan."
        ),
    )


# ======================================================================== #
# 5.3 — Ortiqcha komissiya
# ======================================================================== #


@dataclass(frozen=True, slots=True)
class CommissionCheck:
    """Bitta SKU bo'yicha davr ichidagi komissiya."""

    sku: str
    sales_amount: Decimal      # sotuv summasi
    charged_commission: Decimal  # Uzum ushlagan
    expected_pct: Decimal      # shartnomadagi foiz (API'dan keladi)

    @property
    def expected_commission(self) -> Decimal:
        return _money(self.sales_amount * self.expected_pct / Decimal("100"))

    @property
    def diff(self) -> Decimal:
        """Musbat — ortiqcha ushlangan."""
        return _money(self.charged_commission - self.expected_commission)


def audit_commission(check: CommissionCheck) -> Finding | None:
    """5.3 — kutilgan va ushlangan komissiya farqi.

    Kichik farqlar (yaxlitlash) e'tiborga olinmaydi.
    """
    diff = check.diff
    if diff <= COMMISSION_MIN_DIFF:
        return None

    return Finding(
        kind=DiscrepancyKind.OVER_COMMISSION,
        sku=check.sku,
        qty=0,  # komissiyada dona yo'q
        amount=diff,
        status=DiscrepancyStatus.NEW,
        details=(
            f"Sotuv: {check.sales_amount} so'm. "
            f"Kutilgan komissiya ({check.expected_pct}%): "
            f"{check.expected_commission} so'm. "
            f"Ushlangan: {check.charged_commission} so'm. "
            f"Ortiqcha: {diff} so'm."
        ),
    )


# ======================================================================== #
# 5.4 — Logistika
# ======================================================================== #


@dataclass(frozen=True, slots=True)
class DimensionCheck:
    """Kartochkadagi va Uzum omborda o'lchagan габарит guruhi.

    Farq bo'lsa — logistika boshqa tarif bo'yicha hisoblangan. Bu
    ortiqcha ushlashning eng keng tarqalgan sababi va uni seller
    kartochkani tuzatib darhol to'xtata oladi.
    """

    sku: str
    card_group: str | None       # `dimensionalGroup` — kartochkada
    actual_group: str | None     # `actualDimensionalGroup` — omborda
    logistics_paid: Decimal = Decimal("0")  # davr ichida to'langan logistika
    orders_count: int = 0

    @property
    def mismatched(self) -> bool:
        if not self.card_group or not self.actual_group:
            return False
        return self.card_group.strip().lower() != self.actual_group.strip().lower()


def audit_dimension_mismatch(check: DimensionCheck) -> Finding | None:
    """5.4 — kartochkadagi o'lcham haqiqiydan farq qiladi.

    Summani "ortiqcha ushlangan" deb ko'rsatmaymiz — aniq tarif jadvali
    bizda yo'q. To'langan logistikani ko'rsatamiz va tekshirishni
    taklif qilamiz. Status har doim `WATCHING` (SPEC 9.5).
    """
    if not check.mismatched:
        return None

    return Finding(
        kind=DiscrepancyKind.LOGISTICS,
        sku=check.sku,
        qty=check.orders_count,
        amount=_money(check.logistics_paid),
        status=DiscrepancyStatus.WATCHING,
        details=(
            f"O'lcham nomuvofiqligi: kartochkada «{check.card_group}», "
            f"Uzum omborda «{check.actual_group}» deb o'lchagan. "
            f"Bu davrda {check.orders_count} ta buyurtma bo'yicha "
            f"{_money(check.logistics_paid)} so'm logistika to'langan. "
            f"Kartochkadagi o'lcham va og'irlikni tekshiring — noto'g'ri "
            f"bo'lsa, logistika ortiqcha hisoblangan bo'lishi mumkin."
        ),
    )


@dataclass(frozen=True, slots=True)
class LogisticsCheck:
    sku: str
    expected_fee: Decimal  # kartochkadagi o'lcham/og'irlik bo'yicha tarif
    charged_fee: Decimal   # haqiqatda ushlangan

    @property
    def diff(self) -> Decimal:
        return _money(self.charged_fee - self.expected_fee)

    @property
    def diff_pct(self) -> Decimal:
        if self.expected_fee == 0:
            # Kutilgan 0 bo'lsa, foizni hisoblab bo'lmaydi. Ushlangan bor
            # bo'lsa — bu o'zi shubhali.
            return Decimal("100") if self.charged_fee > 0 else Decimal("0")
        return _money(self.diff / self.expected_fee * Decimal("100"))


def audit_logistics(check: LogisticsCheck) -> Finding | None:
    """5.4 — logistika to'lovi tarifdan qanchalik chetlashgan.

    Chetlanish {LOGISTICS_TOLERANCE_PCT}% dan oshsa — tekshirish kerak.
    Bu audit eng noaniq: o'lcham kartochkada noto'g'ri bo'lishi ham
    mumkin. Shuning uchun natija har doim `WATCHING`.
    """
    if check.diff <= 0:
        return None

    if check.diff_pct <= LOGISTICS_TOLERANCE_PCT:
        return None

    return Finding(
        kind=DiscrepancyKind.LOGISTICS,
        sku=check.sku,
        qty=0,
        amount=check.diff,
        status=DiscrepancyStatus.WATCHING,  # tasdiqlash kerak
        details=(
            f"Tarif bo'yicha kutilgan: {check.expected_fee} so'm. "
            f"Ushlangan: {check.charged_fee} so'm. "
            f"Farq: {check.diff} so'm ({check.diff_pct}%). "
            f"Tovar o'lchami/og'irligi to'g'ri ko'rsatilganini tekshiring."
        ),
    )


# ======================================================================== #
# 5.5 — Kompensatsiya sverkasi
# ======================================================================== #


@dataclass(frozen=True, slots=True)
class CompensationCheck:
    """Aniqlangan zarar uchun Uzum to'lov qildimi."""

    sku: str
    claimed_amount: Decimal  # tan olingan zarar
    paid_amount: Decimal     # kelgan kompensatsiya
    qty: int = 0

    @property
    def shortfall(self) -> Decimal:
        """To'lanmagan qism."""
        return _money(self.claimed_amount - self.paid_amount)


def audit_compensation(check: CompensationCheck) -> Finding | None:
    """5.5 — kompensatsiya kelmadi yoki kam keldi.

    Raqobatchida bu audit yo'q — bizning ustunligimiz. Uzum "to'ladim"
    deydi, biz haqiqatan tushganini tekshiramiz.
    """
    shortfall = check.shortfall
    if shortfall <= 0:
        return None  # to'liq yoki ortig'i bilan to'langan

    if check.paid_amount == 0:
        reason = "Kompensatsiya umuman kelmagan."
    else:
        reason = "Kompensatsiya to'liq kelmagan."

    return Finding(
        kind=DiscrepancyKind.MISSING_COMPENSATION,
        sku=check.sku,
        qty=check.qty,
        amount=shortfall,
        status=DiscrepancyStatus.NEW,
        details=(
            f"{reason} Tan olingan zarar: {check.claimed_amount} so'm. "
            f"To'langan: {check.paid_amount} so'm. "
            f"Yetishmayapti: {shortfall} so'm."
        ),
    )


# ======================================================================== #
# Umumiy yig'indi
# ======================================================================== #


def total_claimable(findings: list[Finding]) -> Decimal:
    """Da'vo qilinadigan umumiy summa (kuzatuvdagilar hisobga olinmaydi).

    Sellerga aynan shu raqam ko'rsatiladi — kuzatuvdagilarni qo'shsak,
    va'da qilingan summa da'voda tasdiqlanmay qoladi.
    """
    return _money(sum((f.amount for f in findings if f.is_claimable), Decimal("0")))


def total_watching(findings: list[Finding]) -> Decimal:
    """Kuzatuvdagi (hali da'vo qilinmaydigan) summa."""
    return _money(sum((f.amount for f in findings if not f.is_claimable), Decimal("0")))
