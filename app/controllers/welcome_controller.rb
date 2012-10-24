class WelcomeController < ApplicationController
  def index
  	@loose_links = []
  	Link.all.each do |l|
  		if l.tags.count == 0
  			@loose_links << l
  		end
  	end
  end
end
