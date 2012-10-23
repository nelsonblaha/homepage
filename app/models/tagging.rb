class Tagging < ActiveRecord::Base
  attr_accessible :item_id, :tag_id
  belongs_to :tag
  belongs_to :link, foreign_key: :item_id
end
