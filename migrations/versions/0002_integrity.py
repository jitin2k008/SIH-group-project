"""Preserve records, convert numeric/date columns and add new order fields."""
from alembic import op
import sqlalchemy as sa
revision = '0002_integrity'
down_revision = '0001_legacy'
branch_labels = depends_on = None


def upgrade():
    # PostgreSQL transactional DDL: invalid old data causes rollback, not silent deletion.
    numeric = {
        'products': [('quantity',14,3), ('price_per_unit',16,2)],
        'orders': [('quantity',14,3), ('total_price',18,2)],
        'transporters':[('capacity_kg',14,3)],
        'deliveries':[('transport_cost',18,2)],
    }
    for table, fields in numeric.items():
        for name, precision, scale in fields:
            op.alter_column(table, name, type_=sa.Numeric(precision, scale),
                postgresql_using=f'{name}::numeric({precision},{scale})', existing_nullable=False)
    for table in ['orders','deliveries']:
        op.alter_column(table, 'created_at', type_=sa.DateTime(timezone=True),
            postgresql_using="created_at::timestamp AT TIME ZONE 'UTC'", nullable=False)
    op.add_column('products', sa.Column('is_active',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.alter_column('products', 'is_active', server_default=None)
    for name, datatype in [
        ('expires_at',sa.DateTime(timezone=True)), ('quote_id',sa.String()),
        ('product_name',sa.String()), ('unit',sa.String()), ('unit_price',sa.Numeric(16,2)),
        ('pickup_location',sa.String()), ('transport_cost',sa.Numeric(16,2)),
        ('grand_total',sa.Numeric(18,2)), ('distance_km',sa.Numeric(12,2)),
        ('vehicle_type',sa.String()), ('vehicle_rate',sa.Numeric(10,2)),
        ('pickup_latitude',sa.Numeric(10,7)), ('pickup_longitude',sa.Numeric(10,7)),
        ('delivery_latitude',sa.Numeric(10,7)), ('delivery_longitude',sa.Numeric(10,7))]:
        op.add_column('orders',sa.Column(name,datatype,nullable=True))
    op.create_unique_constraint('uq_orders_quote_id','orders',['quote_id'])
    # Best-known names/units are snapshotted; historical prices/quotes are NOT invented.
    op.execute('UPDATE orders o SET product_name=p.name, unit=p.unit, pickup_location=p.location FROM products p WHERE p.id=o.product_id')
    op.execute('UPDATE orders o SET pickup_location=d.pickup_location FROM deliveries d WHERE d.order_id=o.id')
    # Give existing pending orders 24h from migration, rather than silently expiring immediately.
    op.execute("UPDATE orders SET expires_at=CURRENT_TIMESTAMP + INTERVAL '24 hours' WHERE status='pending'")
    constraints = [
        ('users','ck_user_role',"role IN ('farmer','buyer','transporter')"),
        ('products','ck_product_quantity','quantity >= 0 AND quantity <= 1000000'),
        ('products','ck_product_price','price_per_unit > 0 AND price_per_unit <= 100000000'),
        ('orders','ck_order_quantity','quantity > 0 AND quantity <= 1000000'),
        ('orders','ck_order_price','total_price >= 0 AND total_price <= 100000000000000'),
        ('orders','ck_order_status',"status IN ('pending','accepted','rejected','completed','delivery_failed','returned','cancelled','expired')"),
        ('transporters','ck_transporter_capacity','capacity_kg > 0 AND capacity_kg <= 1000000'),
        ('transporters','ck_transporter_availability',"is_available IN ('available','busy')"),
        ('deliveries','ck_delivery_cost','transport_cost >= 0 AND transport_cost <= 100000000000000'),
        ('deliveries','ck_delivery_status',"status IN ('available','assigned','picked_up','in_transit','delivered','failed','returned')"),
    ]
    for table,name,condition in constraints:
        op.create_check_constraint(name,table,condition)
    for table,columns in {'products':['farmer_id'],'orders':['buyer_id','product_id','status','expires_at'],
                          'deliveries':['transporter_id','status']}.items():
        for column in columns:
            op.create_index(f'ix_{table}_{column}',table,[column])
    # Existing unused farmer.rating stays in the DB so user data is not destroyed.


def downgrade():
    raise RuntimeError('Restore a verified backup to revert this data migration; lossy downgrade is disabled.')
