# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2004-2015 Pexego Sistemas Informáticos All Rights Reserved
#    $Jesús Ventosinos Mayor <jesus@pexego.es>$
#    Copyright (C) 2015 Comunitea Servicios Tecnológicos All Rights Reserved
#    $Omar Castiñeira Saaevdra <omar@comunitea.com>$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp import models, fields, api, exceptions, _
from datetime import datetime, date, time, timedelta

import logging
logger = logging.getLogger(__name__)

class rappel(models.Model):
    _name = 'rappel'
    _description = 'Rappel Model'

    CALC_MODE = [('fixed', 'Fixed'), ('variable', 'Variable')]
    QTY_TYPE = [('quantity', 'Quantity'), ('value', 'Value')]
    CALC_AMOUNT = [('percent', 'Percent'), ('qty', 'Quantity')]

    name = fields.Char('Concept', size=255, required=True)
    type_id = fields.Many2one('rappel.type', 'Type', required=True)
    qty_type = fields.Selection(QTY_TYPE, 'Quantity type', required=True,default='value')
    calc_mode = fields.Selection(CALC_MODE, 'Fixed/Variable', required=True)
    fix_qty = fields.Float('Fix')
    sections = fields.One2many('rappel.section', 'rappel_id', 'Sections')
    global_application = fields.Boolean('Global', default=True)
    product_id = fields.Many2one('product.product', 'Product')
    product_categ_id = fields.Many2one('product.category', 'Category')
    calc_amount = fields.Selection(CALC_AMOUNT, 'Percent/Quantity',
                                   required=True)
    customer_ids = fields.One2many("res.partner.rappel.rel", "rappel_id",
                                   "Customers")
    advice_timing_ids=fields.One2many("rappel.advice.email", "rappel_id", "Email Timing Advice")


    @api.constrains('global_application', 'product_id', 'product_categ_id')
    def _check_application(self):
        if not self.global_application and not self.product_id \
                and not self.product_categ_id:
            raise exceptions.\
                ValidationError(_('Product and category are empty'))

    @api.multi
    def get_products(self):
        product_obj = self.env['product.product']
        product_ids = self.env['product.product']
        for rappel in self:
            if not rappel.global_application:
                if rappel.product_id:
                    product_ids += rappel.product_id
                elif rappel.product_categ_id:
                    product_ids += product_obj.search(
                        [('categ_id', '=', rappel.product_categ_id.id)])
            else:
                product_ids += product_obj.search([])
        return [x.id for x in product_ids]

    @api.model
    def compute_rappel(self):
        if not self.ids:
            rappels = self.search([])
        else:
            rappels = self
        rappel_infos = self.env["rappel.current.info"].search([])
        if rappel_infos:
            rappel_infos.unlink()
        for rappel in rappels:
            products = rappel.get_products()
            for customer in rappel.customer_ids:
                period = customer._get_next_period()
                if period:
                    invoice_lines, refund_lines = customer.\
                        _get_invoices(period, products)
                    customer.compute(period, invoice_lines, refund_lines,
                                     tmp_model=True)
        self.env["rappel.current.info"].send_rappel_info_mail()


class rappel_section(models.Model):

    _name = 'rappel.section'
    _description = 'Rappel section model'

    @api.multi
    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "%s - %s" % (record.rappel_from,
                                                   record.rappel_until)))

        return result

    rappel_from = fields.Float('From', required=True)
    rappel_until = fields.Float('Until')
    percent = fields.Float('Value', required=True)
    rappel_id = fields.Many2one('rappel', 'Rappel')


class tax_rappel_calculated(models.Model):

    _name = 'tax.rappel.calculated'

    rappel_id = fields.Many2one('rappel.calculated', 'Rappel calculated', required=True)
    tax_id = fields.Many2one('account.tax.code', 'Tax', required=True)
    base = fields.Float('Base', required=True)
    quantity = fields.Float('Quantity')



class rappel_calculated(models.Model):

    _name = 'rappel.calculated'

    partner_id = fields.Many2one('res.partner', 'Customer', required=True)
    date_start = fields.Date('Date start', required=True)
    date_end = fields.Date('Date end', required=True)
    quantity = fields.Float('Quantity', required=True, default=0.0)
    rappel_id = fields.Many2one('rappel', 'Rappel', required=True)
    invoice_id = fields.Many2one("account.invoice", "Invoice", readonly=True)


    @api.multi
    def  button_calcular_rappel(self):
        rapel_calculado = 0
        rapel_base = 0
        rapel_taxes=[]
        this_invoice = self.env["account.invoice"]
        this_tax_base = self.env["tax.rappel.calculated"]
        fmt = '%Y-%m-%d'

        self.write({'quantity':0})
        base_iva = this_tax_base.search([('rappel_id','=',self.id)])
        if base_iva:
            base_iva[0].base = 0
            base_iva[0].quantity = 0

       
        for record in self:
            d_start = datetime.strptime(record.date_start, fmt)
            d_end = datetime.strptime(record.date_end, fmt)
            factura = this_invoice.search([('partner_id','=',record.partner_id.id),('date_invoice','>=',d_start),('date_invoice','<=',d_end),('state','not in',['draft','cancel'])])
            for f in factura:
                logger.error('Valor para factura en calcular rapel %s'%f.number)
                rapel_base += f.amount_untaxed
                if f.tax_line:
                    logger.error('Valor para tax en factura en calcular rapel %s'%f.tax_line)
                    for t in f.tax_line:
                        base_iva = this_tax_base.search([('rappel_id','=',self.id),('tax_id','=',t.base_code_id.id)])
                        if base_iva:
                            base_iva[0].base += t.base_amount
                        else:
                            tax_base_vals = {'rappel_id': self.id,
                                    'tax_id': t.base_code_id.id,
                                    'base': t.base_amount or 0}
                            this_tax_base.create(tax_base_vals)

            if record.rappel_id.calc_amount == 'percent':
                if record.rappel_id.calc_mode == 'variable':
                    if record.rappel_id.sections:
                        for sect in record.rappel_id.sections:
                            if sect.rappel_from > rapel_base:
                                continue
                            else:
                                if sect.rappel_until < rapel_base:
                                    continue
                                else:
                                    rapel_calculado = rapel_base * (sect.percent/100)
                                    cuota_iva = this_tax_base.search([('rappel_id','=',self.id)])
                                    for c in cuota_iva:
                                        c.quantity = c.base * (sect.percent/100)
                    else:
                        raise exceptions.ValidationError(_('No se han definido los intervalos'))
                else:
                    rapel_calculado = rapel_base * (record.rappel_id.fix_qty/100)
                    cuota_iva = this_tax_base.search([('rappel_id','=',self.id)])
                    for c in cuota_iva:
                        c.quantity = c.base * (record.rappel_id.fix_qty/100)
            else:
                if record.rappel_id.calc_mode == 'variable':
                    if record.rappel_id.sections:
                        for sect in record.rappel_id.sections:
                            if sect.rappel_from > rapel_base:
                                continue
                            else:
                                if sect.rappel_until < rapel_base:
                                    continue
                                else:
                                    rapel_calculado = sect.percent
                                    cuota_iva = this_tax_base.search([('rappel_id','=',self.id)])
                                    for c in cuota_iva:
                                        c.quantity = (c.base/rapel_base) * sect.percent
                    else:
                        raise exceptions.ValidationError(_('No se han definido los intervalos'))
                else:
                    rapel_calculado = record.rappel_id.fix_qty
                    cuota_iva = this_tax_base.search([('rappel_id','=',self.id)])
                    for c in cuota_iva:
                        c.quantity = (c.base/rapel_base) * record.rappel_id.fix_qty



        logger.error('Valor para rapel calculado %s'%rapel_calculado)
        self.write({'quantity':rapel_calculado})

