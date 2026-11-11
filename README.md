# Photo Sorter

Aplikasi Windows untuk menyortir foto. Versi saat ini: **0.3.0 beta**.
Antarmuka menggunakan gaya hand-drawn dengan warna seperti kertas dan garis sketsa.

## Menjalankan aplikasi

Unduh `PhotoSorter.exe` dari bagian **Releases** di GitHub lalu buka file tersebut. Tidak perlu memasang Python.

## Membuat rilis

Simpan perubahan kode ke repo, lalu buat dan push tag versi baru, misalnya `v0.3.1-beta`. Workflow GitHub Actions akan membangun EXE Windows dan melampirkannya ke GitHub Release. Tag yang mengandung `-` diterbitkan sebagai prerelease. Workflow juga dapat dijalankan manual dari tab **Actions** dengan mengisi nama tag.

Di aplikasi, klik **Cek update** pada menu utama. Jika ada versi yang lebih baru, aplikasi membuka halaman rilis agar pengguna dapat mengunduh EXE.

Pemeriksaan update membaca rilis publik melalui GitHub API untuk `PaleSalome/PhotoSorter`. Aplikasi tidak mengunduh atau mengganti file EXE secara otomatis.

Tampilan sortir menyesuaikan ukuran jendela dan resolusi layar; ukuran jendela yang tersimpan akan dibatasi agar tetap muat di layar.

Format foto RAW Canon `.CR3` juga didukung melalui `rawpy`/LibRaw.
