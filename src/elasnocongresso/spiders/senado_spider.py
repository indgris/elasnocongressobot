import scrapy
from scrapy.spiders import XMLFeedSpider
from scrapy.exporters import CsvItemExporter
import redis
from datetime import datetime, timedelta
from .theme_assert import assert_theme

class SenadoSpider(XMLFeedSpider):
    dia_anterior = (datetime.now() - timedelta(1)).strftime('%d')
    mes_anterior = (datetime.now() - timedelta(1)).strftime('%m')
    ano_anterior = (datetime.now() - timedelta(1)).strftime('%Y')

    name = 'senado'
    allowed_domains = ['legis.senado.leg.br']
    start_urls = ['https://legis.senado.leg.br/dadosabertos/materia/tramitando?data=20230624']
    iterator = 'iternodes'
    itertag = 'Materia'

    def __init__(self):
        self.file = open("senado.csv", 'wb')
        self.exporter = CsvItemExporter(self.file)
        self.exporter.start_exporting()
        self.redis = redis.Redis(host='redis', port=6379, db=0)

    def parse_node(self, response, node):
        tries = 1
        try:
            item = dict()
            item['CodigoMateria'] = node.xpath('IdentificacaoMateria/CodigoMateria/text()').extract_first()
            item['SiglaCasaIdentificacaoMateria'] = node.xpath('IdentificacaoMateria/SiglaCasaIdentificacaoMateria/text()').extract_first()
            item['NomeCasaIdentificacaoMateria'] = node.xpath('IdentificacaoMateria/NomeCasaIdentificacaoMateria/text()').extract_first()
            item['SiglaSubtipoMateria'] = node.xpath('IdentificacaoMateria/SiglaSubtipoMateria/text()').extract_first()
            item['NumeroMateria'] = node.xpath('IdentificacaoMateria/NumeroMateria/text()').extract_first()
            item['AnoMateria'] = node.xpath('IdentificacaoMateria/AnoMateria/text()').extract_first()
            item['IdentificacaoProcesso'] = node.xpath('IdentificacaoMateria/IdentificacaoProcesso/text()').extract_first()
            item['DescricaoIdentificacaoMateria'] = node.xpath('IdentificacaoMateria/DescricaoIdentificacaoMateria/text()').extract_first()
            item['IndicadorTramitando'] = node.xpath('IdentificacaoMateria/IndicadorTramitando/text()').extract_first()
            item['Ementa'] = node.xpath('Ementa/text()').extract_first()
            item['Autor'] = node.xpath('Autor/text()').extract_first()
            item['DataApresentacao'] = node.xpath('DataApresentacao/text()').extract_first()
            item['DataUltimaAtualizacao'] = node.xpath('DataUltimaAtualizacao/text()').extract_first()

            theme_assertion = assert_theme({"Ementa": item['Ementa']})
            if theme_assertion['row_relevant']:
                item['temas'] = ', '.join(theme_assertion['temas'])

                current_date = datetime.now().isoformat()
                self.redis.set(f'savepoint_senado', f'{item["CodigoMateria"]}, {current_date}')

                row_url = f"https://legis.senado.leg.br/dadosabertos/materia/{item['CodigoMateria']}"
                row_request = scrapy.Request(row_url, callback=self.parse_row_data)
                row_request.meta['item'] = item
                yield row_request

        except:
            logging.info(f'Erro ao processar linha, tentativa: {tries}')
            self.redis.set(f'savepoint_senado_erro:{item["CodigoMateria"]}', f'{current_date}')
            if (tries < 3):
                tries += 1
                yield scrapy.Request(response.url, callback=self.parse_node, dont_filter=True)

    def parse_row_data(self, response): 
        item = response.meta['item']
        
        item['ApelidoMateria'] = response.xpath('//ApelidoMateria/text()').extract_first()
        item['Autor'] = response.xpath('//Autor/text()').extract_first()
        item['CasaIniciadoraNoLegislativo'] = response.xpath('//CasaIniciadoraNoLegislativo/text()').extract_first()
        item['NumeroRepublicacaoMpv'] = response.xpath('//NumeroRepublicacaoMpv/text()').extract_first()
        item['IndicadorComplementar'] = response.xpath('//IndicadorComplementar/text()').extract_first()
        item['DataApresentacao'] = response.xpath('//DataApresentacao/text()').extract_first()
        item['DataAssinatura'] = response.xpath('//DataAssinatura/text()').extract_first()
        item['AssuntoEspecificoCod'] = response.xpath('Assunto/AssuntoEspecifico/Codigo').extract_first()
        item['AssuntoEspecificoDesc'] = response.xpath('Assunto/AssuntoEspecifico/Descricao').extract_first()
        item['AssuntoGeralCod'] = response.xpath('Assunto/AssuntoGeral/Codigo').extract_first()
        item['AssuntoGeralDesc'] = response.xpath('Assunto/AssuntoGeral/Descricao').extract_first()

        self.exporter.export_item(item)
        return item

    def parse_authors(self, response):
        item = response.meta['item']

        item['nome'] = response.xpath('//autor/nome/text()').extract_first()
        item['tipo'] = response.xpath('//autor/tipo/text()').extract_first()

        self.exporter.export_item(item)
        return item

    def close_spider(self, spider):
        self.exporter.finish_exporting()
        self.file.close()