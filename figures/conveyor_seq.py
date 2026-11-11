import sys
from seqdiag import draw
P = ['MCPクライアント\n（エージェント）', 'conveyor-mcp\n（server.py）', 'Arduino UNO', 'リレー\n（ベルト）']
CL, SV, AR, RL = P
draw(P, [
    ('group', 'サーバーの起動時', [
        ('msg', SV, AR, 'シリアルポートを開く（Arduino がリセット）'),
        ('note', SV, '2秒待つ'),
        ('msg', SV, AR, "'0'"),
        ('msg', AR, RL, 'LOW（OFF）'),
        ('reply', AR, SV, 'OFF'),
        ('note', SV, 'OFF を確認できなければ起動失敗'),
    ]),
    ('msg', CL, SV, 'start_conveyor'),
    ('msg', SV, AR, "'1'"),
    ('msg', AR, RL, 'HIGH（ON）'),
    ('reply', AR, SV, 'ON'),
    ('reply', SV, CL, '成功（指令を受け付けたことだけ）'),
    ('group', 'alt: 1.5秒以内に ON が返らない場合', [
        ('msg', SV, AR, "'0'（念のため停止を送る）"),
        ('note', SV, 'fault を記録'),
        ('reply', SV, CL, 'エラー（再起動まで開始を拒否）'),
    ]),
], sys.argv[1], col_width=3.8)
