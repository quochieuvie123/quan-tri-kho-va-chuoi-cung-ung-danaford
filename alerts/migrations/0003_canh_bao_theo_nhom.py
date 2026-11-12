import django.db.models.deletion

from django.db import migrations, models


def chuyen_nguong_cu(apps, schema_editor):
    Nguong = apps.get_model("alerts", "NguongCanhBao")
    CanhBao = apps.get_model("alerts", "CanhBao")

    db = schema_editor.connection.alias

    # Giữ thông tin kho của các cảnh báo thiếu hàng cũ.
    for cb in CanhBao.objects.using(db).exclude(loai="TON_LAU"):
        if cb.kho_id:
            cb.cac_kho.add(cb.kho_id)

    # Kết thúc hiệu lực cách tính cũ, không xóa lịch sử.
    CanhBao.objects.using(db).exclude(loai="TON_LAU").update(
        con_hieu_luc=False,
    )

    cac_nhom = {}

    for nguong in Nguong.objects.using(db).order_by("pk"):
        cac_tu = nguong.ten_xe.strip().split()

        if cac_tu and cac_tu[0].casefold() == "ford":
            cac_tu = cac_tu[1:]

        dong_xe = ""

        for ten in [
            "Ranger",
            "Everest",
            "Territory",
            "Explorer",
            "Transit",
        ]:
            if cac_tu and cac_tu[0].casefold() == ten.casefold():
                dong_xe = ten
                break

        if not dong_xe:
            raise RuntimeError(
                "Không nhận diện được dòng xe của ngưỡng cũ."
            )

        mau_sac = (nguong.mau_sac or "").strip()
        nhom = (dong_xe, mau_sac)

        if nhom in cac_nhom:
            CanhBao.objects.using(db).filter(
                nguong_id=nguong.pk,
            ).update(
                nguong_id=cac_nhom[nhom],
            )

            nguong.delete(using=db)

        else:
            nguong.ten_xe = dong_xe
            nguong.mau_sac = mau_sac

            if dong_xe == "Everest" and mau_sac.casefold() == "trắng tuyết":
                nguong.ton_toi_thieu = 3
            else:
                nguong.ton_toi_thieu = 2

            nguong.save(using=db)
            cac_nhom[nhom] = nguong.pk


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0002_canhbao"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="nguongcanhbao",
            name="alerts_nguong_kho_xe_mau_unique",
        ),

        migrations.AlterField(
            model_name="canhbao",
            name="kho",
            field=models.ForeignKey(
                to="database.kho",
                on_delete=django.db.models.deletion.PROTECT,
                null=True,
                blank=True,
                verbose_name="Kho của cảnh báo tồn lâu",
            ),
        ),

        migrations.AddField(
            model_name="canhbao",
            name="cac_kho",
            field=models.ManyToManyField(
                to="database.kho",
                blank=True,
                related_name="canh_bao_lien_quan",
                verbose_name="Các kho liên quan",
            ),
        ),

        migrations.RunPython(chuyen_nguong_cu),

        migrations.RemoveField(
            model_name="nguongcanhbao",
            name="kho",
        ),

        migrations.AlterField(
            model_name="nguongcanhbao",
            name="ten_xe",
            field=models.CharField(
                "Dòng xe",
                max_length=255,
            ),
        ),

        migrations.AddConstraint(
            model_name="nguongcanhbao",
            constraint=models.UniqueConstraint(
                fields=("ten_xe", "mau_sac"),
                name="alerts_nguong_dong_mau_unique",
            ),
        ),
    ]
