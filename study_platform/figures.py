"""동일 입력에서 동일 SVG를 생성하는 과학 도표. 외부 자원이나 솔버를 사용하지 않는다."""
import xml.etree.ElementTree as ET


def comparison_svg(comparison):
    root = ET.Element('svg', xmlns='http://www.w3.org/2000/svg', width='1000', height='420', viewBox='0 0 1000 420')
    ET.SubElement(root, 'rect', width='1000', height='420', fill='white')
    def text(x, y, value, color='#222'):
        ET.SubElement(root, 'text', x=str(x), y=str(y), fill=color, **{'font-size': '14', 'font-family': 'sans-serif'}).text = str(value)
    text(45, 25, 'Normalized tracer: cell-volume mean concentration')
    text(45, 47, 'C/C_ref (not physical fumigant concentration)')
    rows = comparison['rows']
    if rows:
        end = max(r['metrics']['physical_end_s'] for r in rows)
        upper = max(max(r['metrics']['mean_C']) for r in rows)*1.05
        ET.SubElement(root, 'path', d='M60 65 V320 H970', fill='none', stroke='#555')
        for i in range(6):
            text(5, 320-i*48, f'{upper*i/5:.2f}')
            text(60+i*180, 345, f'{end*i/5:.2f}')
        text(820, 373, 'Physical time (s)')
        for i, row in enumerate(rows):
            color = ('#167b70', '#c55d29', '#765caa', '#277eae')[i % 4]
            points = ' '.join(f'{60+t/end*900:.5f},{320-v/upper*240:.5f}'
                              for t, v in zip(row['metrics']['times'], row['metrics']['mean_C']))
            ET.SubElement(root, 'polyline', points=points, fill='none', stroke=color, **{'stroke-width': '2'})
            text(60+(i % 4)*220, 392+(i//4)*16, row['attempt'][:12], color)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
